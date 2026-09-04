from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing import (
    PALETTES,
    TemperatureUnit,
    format_temperature,
    render_frame,
)
from lepton_radiometry_studio.sources import FrameSource, StillFileSource, SyntheticSource
from lepton_radiometry_studio.storage import Hdf5RecordingWriter, save_still
from lepton_radiometry_studio.ui.thermal_canvas import ThermalCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lepton Radiometry Studio")
        self.resize(1080, 720)

        self._source: FrameSource = SyntheticSource()
        self._current_frame: Optional[ThermalFrame] = None
        self._current_rgb = None
        self._recording: Optional[Hdf5RecordingWriter] = None
        self._frame_times: list[float] = []
        self._unit = TemperatureUnit.CELSIUS

        self._build_ui()
        self._build_menu()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._acquire_frame)
        self._start_source(self._source)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        self.canvas = ThermalCanvas()
        self.canvas.pixel_hovered.connect(self._show_hover)
        self.canvas.hover_left.connect(lambda: self.hover_value.setText("Move over image"))
        root.addWidget(self.canvas, 1)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(12)
        sidebar.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel("Lepton Radiometry Studio")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        sidebar.addWidget(title)

        source_group = QGroupBox("Source")
        source_layout = QFormLayout(source_group)
        self.source_value = QLabel(self._source.name)
        source_layout.addRow("Input", self.source_value)
        self.fps_value = QLabel("—")
        source_layout.addRow("Frame rate", self.fps_value)
        sidebar.addWidget(source_group)

        display_group = QGroupBox("Display")
        display_layout = QFormLayout(display_group)
        self.palette_combo = QComboBox()
        self.palette_combo.addItems(PALETTES.keys())
        self.palette_combo.currentTextChanged.connect(self._rerender)
        display_layout.addRow("Palette", self.palette_combo)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems([unit.value for unit in TemperatureUnit])
        self.unit_combo.currentTextChanged.connect(self._change_unit)
        display_layout.addRow("Units", self.unit_combo)
        sidebar.addWidget(display_group)

        measurements = QGroupBox("Measurements")
        measurement_layout = QFormLayout(measurements)
        self.hover_value = QLabel("Move over image")
        self.hover_value.setMinimumWidth(220)
        self.minimum_value = QLabel("—")
        self.maximum_value = QLabel("—")
        self.mean_value = QLabel("—")
        self.center_value = QLabel("—")
        measurement_layout.addRow("Cursor", self.hover_value)
        measurement_layout.addRow("Minimum", self.minimum_value)
        measurement_layout.addRow("Maximum", self.maximum_value)
        measurement_layout.addRow("Mean", self.mean_value)
        measurement_layout.addRow("Center", self.center_value)
        sidebar.addWidget(measurements)

        self.capture_button = QPushButton("Capture radiometric still")
        self.capture_button.clicked.connect(self._capture_still)
        sidebar.addWidget(self.capture_button)
        self.record_button = QPushButton("Start radiometric recording")
        self.record_button.clicked.connect(self._toggle_recording)
        sidebar.addWidget(self.record_button)
        self.synthetic_button = QPushButton("Return to synthetic camera")
        self.synthetic_button.clicked.connect(lambda: self._start_source(SyntheticSource()))
        sidebar.addWidget(self.synthetic_button)
        root.addLayout(sidebar)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Synthetic camera connected")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open radiometric still…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_still)
        file_menu.addAction(open_action)
        capture_action = QAction("Capture still", self)
        capture_action.setShortcut("Ctrl+S")
        capture_action.triggered.connect(self._capture_still)
        file_menu.addAction(capture_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _start_source(self, source: FrameSource) -> None:
        self._timer.stop() if hasattr(self, "_timer") else None
        self._source.stop()
        self._source = source
        self._source.start()
        self.source_value.setText(source.name)
        self._frame_times.clear()
        interval_ms = max(1, round(1000.0 / source.nominal_fps))
        self._timer.start(interval_ms)
        self._acquire_frame()
        self.statusBar().showMessage(f"Connected to {source.name}", 4000)

    def _acquire_frame(self) -> None:
        try:
            frame = self._source.next_frame()
            self._current_frame = frame
            self._frame_times.append(time.monotonic())
            self._frame_times = self._frame_times[-30:]
            if self._recording is not None:
                self._recording.append(frame)
            self._rerender()
            self._update_measurements()
            self._update_fps()
        except Exception as exc:  # UI boundary: surface source/storage failures
            self._timer.stop()
            QMessageBox.critical(self, "Frame acquisition failed", str(exc))
            self.statusBar().showMessage("Source disconnected")

    def _rerender(self) -> None:
        if self._current_frame is None:
            return
        self._current_rgb = render_frame(
            self._current_frame, palette=self.palette_combo.currentText()
        )
        self.canvas.set_frame(self._current_frame, self._current_rgb)

    def _update_measurements(self) -> None:
        if self._current_frame is None:
            return
        stats = self._current_frame.statistics()
        center_x = self._current_frame.width // 2
        center_y = self._current_frame.height // 2
        center_c = self._current_frame.temperature_at_celsius(center_x, center_y)
        self.minimum_value.setText(
            f"{format_temperature(stats.minimum_c, self._unit)} at {stats.minimum_xy}"
        )
        self.maximum_value.setText(
            f"{format_temperature(stats.maximum_c, self._unit)} at {stats.maximum_xy}"
        )
        self.mean_value.setText(format_temperature(stats.mean_c, self._unit))
        self.center_value.setText(
            f"{format_temperature(center_c, self._unit)} at ({center_x}, {center_y})"
        )

    def _update_fps(self) -> None:
        if len(self._frame_times) < 2:
            self.fps_value.setText("—")
            return
        elapsed = self._frame_times[-1] - self._frame_times[0]
        fps = (len(self._frame_times) - 1) / elapsed if elapsed else 0.0
        self.fps_value.setText(f"{fps:.2f} FPS")

    def _show_hover(self, x: int, y: int, raw: int, temperature_c: float) -> None:
        self.hover_value.setText(
            f"({x}, {y}) · {format_temperature(temperature_c, self._unit)} · raw {raw}"
        )

    def _change_unit(self, unit_text: str) -> None:
        self._unit = next(unit for unit in TemperatureUnit if unit.value == unit_text)
        self._update_measurements()

    def _capture_still(self) -> None:
        if self._current_frame is None or self._current_rgb is None:
            return
        chosen = QFileDialog.getExistingDirectory(self, "Choose capture location", str(Path.cwd()))
        if not chosen:
            return
        try:
            destination = save_still(
                self._current_frame, Path(chosen), preview_rgb=self._current_rgb
            )
        except Exception as exc:
            QMessageBox.critical(self, "Capture failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {destination}", 8000)

    def _open_still(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open radiometric still",
            str(Path.cwd()),
            "Radiometric frames (thermal.npy thermal.tif thermal.tiff);;All files (*)",
        )
        if not path:
            return
        try:
            self._start_source(StillFileSource(Path(path)))
        except Exception as exc:
            QMessageBox.critical(self, "Could not open still", str(exc))

    def _toggle_recording(self) -> None:
        if self._recording is not None:
            frame_count = self._recording.frame_count
            path = self._recording.path
            self._recording.close()
            self._recording = None
            self.record_button.setText("Start radiometric recording")
            self.statusBar().showMessage(f"Saved {frame_count} frames to {path}", 8000)
            return
        if self._current_frame is None:
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose recording location", str(Path.cwd())
        )
        if not chosen:
            return
        name = datetime.now().strftime("recording_%Y-%m-%d_%H%M%S.h5")
        try:
            self._recording = Hdf5RecordingWriter(
                Path(chosen) / name, self._current_frame
            )
        except Exception as exc:
            QMessageBox.critical(self, "Recording failed", str(exc))
            return
        self.record_button.setText("Stop recording")
        self.statusBar().showMessage("Radiometric recording started", 4000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self._source.stop()
        if self._recording is not None:
            self._recording.close()
        event.accept()

