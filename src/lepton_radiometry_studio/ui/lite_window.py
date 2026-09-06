from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing import (
    PALETTES,
    render_frame,
    render_visual_export,
)
from lepton_radiometry_studio.sources.base import FrameSource
from lepton_radiometry_studio.sources.lepton import LeptonFrameTimeout, LeptonSource
from lepton_radiometry_studio.sources.synthetic import SyntheticSource
from lepton_radiometry_studio.sources.unavailable import CameraUnavailableSource
from lepton_radiometry_studio.storage.recordings import RadiometricRecordingSession
from lepton_radiometry_studio.storage.stills import save_still
from lepton_radiometry_studio.ui.thermal_canvas import ThermalCanvas
from lepton_radiometry_studio.ui.theme import apply_theme, load_theme


class LiteMainWindow(QMainWindow):
    """Low-overhead live viewer and capture interface."""

    def __init__(self, auto_connect: bool = True) -> None:
        super().__init__()
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("LiteMainWindow requires an active QApplication")
        apply_theme(application, load_theme())
        self.setWindowTitle("Lepton Radiometry Lite")
        self.resize(1180, 760)

        self._source: FrameSource = CameraUnavailableSource()
        self._current_frame: Optional[ThermalFrame] = None
        self._recording: Optional[RadiometricRecordingSession] = None
        self._frame_times: list[float] = []
        self._camera_failure_count = 0

        self._build_ui()
        self._build_menu()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._acquire_frame)
        self._show_camera_unavailable()
        if auto_connect:
            QTimer.singleShot(0, self._connect_camera)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.canvas = ThermalCanvas()
        self.canvas.set_show_extrema(False)
        self.canvas.set_measurement_editing_enabled(False)
        root.addWidget(self.canvas, 1)

        sidebar_widget = QWidget()
        sidebar = QVBoxLayout(sidebar_widget)
        sidebar.setContentsMargins(0, 0, 8, 0)
        sidebar.setSpacing(5)
        sidebar.setAlignment(Qt.AlignmentFlag.AlignTop)

        source_group = QGroupBox("Source")
        source_layout = QFormLayout(source_group)
        source_layout.setContentsMargins(10, 12, 10, 8)
        source_layout.setVerticalSpacing(5)
        self.source_value = QLabel("Camera not found")
        source_layout.addRow("Input", self.source_value)
        self.fps_value = QLabel("—")
        source_layout.addRow("Frame rate", self.fps_value)
        self.source_detail_value = QLabel("No live FLIR Lepton detected")
        self.source_detail_value.setWordWrap(True)
        source_layout.addRow("Status", self.source_detail_value)
        source_buttons = QHBoxLayout()
        self.retry_camera_button = QPushButton("Retry camera")
        self.retry_camera_button.clicked.connect(self._connect_camera)
        source_buttons.addWidget(self.retry_camera_button)
        self.ffc_button = QPushButton("Run FFC")
        self.ffc_button.clicked.connect(self._run_ffc)
        source_buttons.addWidget(self.ffc_button)
        source_layout.addRow(source_buttons)
        sidebar.addWidget(source_group)

        capture_group = QGroupBox("Capture")
        capture_layout = QVBoxLayout(capture_group)
        capture_layout.setContentsMargins(10, 12, 10, 9)
        capture_layout.setSpacing(5)
        self.capture_button = QPushButton("Capture radiometric still")
        self.capture_button.clicked.connect(self._capture_still)
        capture_layout.addWidget(self.capture_button)
        still_types = QHBoxLayout()
        self.still_png_toggle = QCheckBox("PNG")
        self.still_tiff_toggle = QCheckBox("TIFF")
        self.still_numpy_toggle = QCheckBox("NPY")
        self.still_metadata_toggle = QCheckBox("JSON")
        for toggle in (
            self.still_png_toggle,
            self.still_tiff_toggle,
            self.still_numpy_toggle,
            self.still_metadata_toggle,
        ):
            toggle.setChecked(True)
            still_types.addWidget(toggle)
        capture_layout.addLayout(still_types)
        self.record_button = QPushButton("Start radiometric recording")
        self.record_button.clicked.connect(self._toggle_recording)
        capture_layout.addWidget(self.record_button)
        video_types = QHBoxLayout()
        self.video_hdf5_toggle = QCheckBox("HDF5")
        self.video_mp4_toggle = QCheckBox("MP4")
        self.video_hdf5_toggle.setChecked(True)
        self.video_mp4_toggle.setChecked(True)
        video_types.addWidget(self.video_hdf5_toggle)
        video_types.addWidget(self.video_mp4_toggle)
        video_types.addStretch(1)
        capture_layout.addLayout(video_types)
        sidebar.addWidget(capture_group)

        display_group = QGroupBox("Display")
        display_layout = QFormLayout(display_group)
        display_layout.setContentsMargins(10, 12, 10, 9)
        display_layout.setVerticalSpacing(6)
        self.palette_combo = QComboBox()
        self.palette_combo.addItems(PALETTES.keys())
        self.palette_combo.currentTextChanged.connect(self._rerender)
        display_layout.addRow("Palette", self.palette_combo)
        self.auto_range_toggle = QCheckBox("Automatic range (per frame)")
        self.auto_range_toggle.setChecked(True)
        self.auto_range_toggle.toggled.connect(self._change_automatic_range)
        display_layout.addRow(self.auto_range_toggle)
        self.display_minimum_spin = QDoubleSpinBox()
        self.display_minimum_spin.setRange(-273.15, 2000.0)
        self.display_minimum_spin.setDecimals(2)
        self.display_minimum_spin.setSuffix(" °C")
        self.display_minimum_spin.setValue(0.0)
        self.display_minimum_spin.setEnabled(False)
        self.display_minimum_spin.valueChanged.connect(self._change_manual_range)
        display_layout.addRow("Minimum", self.display_minimum_spin)
        self.display_maximum_spin = QDoubleSpinBox()
        self.display_maximum_spin.setRange(-273.14, 2000.01)
        self.display_maximum_spin.setDecimals(2)
        self.display_maximum_spin.setSuffix(" °C")
        self.display_maximum_spin.setValue(100.0)
        self.display_maximum_spin.setEnabled(False)
        self.display_maximum_spin.valueChanged.connect(self._change_manual_range)
        display_layout.addRow("Maximum", self.display_maximum_spin)
        sidebar.addWidget(display_group)
        sidebar.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar_widget)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(400)
        self.sidebar_scroll = scroll
        root.addWidget(scroll)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        self.file_menu = menu_bar.addMenu("File")
        self.capture_action = QAction("Capture still", self)
        self.capture_action.setShortcut("Ctrl+S")
        self.capture_action.triggered.connect(self._capture_still)
        self.file_menu.addAction(self.capture_action)
        self.file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self.file_menu.addAction(quit_action)

        self.camera_menu = menu_bar.addMenu("Camera")
        retry_action = QAction("Retry camera", self)
        retry_action.triggered.connect(self._connect_camera)
        self.camera_menu.addAction(retry_action)
        self.ffc_action = QAction("Run flat-field correction", self)
        self.ffc_action.triggered.connect(self._run_ffc)
        self.camera_menu.addAction(self.ffc_action)
        self.camera_menu.addSeparator()
        self.synthetic_action = QAction("Use synthetic demo", self)
        self.synthetic_action.triggered.connect(
            lambda: self._start_source(SyntheticSource())
        )
        self.camera_menu.addAction(self.synthetic_action)

    def _start_source(self, source: FrameSource) -> None:
        self._finish_recording()
        self._timer.stop()
        self._source.stop()
        self._source = source
        source.start()
        self._frame_times.clear()
        self._camera_failure_count = 0
        self.source_value.setText(source.name)
        is_camera = isinstance(source, LeptonSource)
        self.source_detail_value.setText(
            "Live radiometric GPIO camera"
            if is_camera
            else "Demo data; no camera hardware"
        )
        self.ffc_button.setEnabled(is_camera)
        self.ffc_action.setEnabled(is_camera)
        interval_ms = max(1, round(1000.0 / source.nominal_fps))
        self._timer.start(interval_ms)
        self.capture_button.setEnabled(True)
        self.capture_action.setEnabled(True)
        self.record_button.setEnabled(True)
        self._acquire_frame()
        self.statusBar().showMessage(f"Connected to {source.name}", 4000)

    def _connect_camera(self) -> None:
        self._finish_recording()
        self._timer.stop()
        self._source.stop()
        self._source = CameraUnavailableSource()
        self._current_frame = None
        self.canvas.clear_frame("Looking for camera…")
        self.source_value.setText("Looking for camera…")
        self.source_detail_value.setText("Checking I²C and SPI")
        self.statusBar().showMessage("Looking for a FLIR Lepton camera")
        try:
            source = LeptonSource.autodetect()
        except Exception as exc:
            self._show_camera_unavailable(str(exc))
            return
        self._start_source(source)

    def _show_camera_unavailable(self, detail: str = "") -> None:
        self._timer.stop()
        self._source.stop()
        self._source = CameraUnavailableSource()
        self._current_frame = None
        self._frame_times.clear()
        self._camera_failure_count = 0
        self.canvas.clear_frame(
            "Camera not found\n\nCheck camera power, SPI/I²C wiring, and permissions, "
            "then click Retry camera."
        )
        self.source_value.setText("Camera not found")
        self.source_detail_value.setText(detail or "No live FLIR Lepton detected")
        self.fps_value.setText("—")
        self.capture_button.setEnabled(False)
        self.capture_action.setEnabled(False)
        self.record_button.setEnabled(False)
        self.ffc_button.setEnabled(False)
        self.ffc_action.setEnabled(False)
        self.statusBar().showMessage("Camera not found")

    def _run_ffc(self) -> None:
        try:
            self._source.run_ffc()
        except Exception as exc:
            QMessageBox.warning(self, "FFC failed", str(exc))
            return
        self.statusBar().showMessage("Flat-field correction completed", 5000)

    def _acquire_frame(self) -> None:
        try:
            frame = self._source.next_frame()
            self._camera_failure_count = 0
            self._current_frame = frame
            self._frame_times.append(time.monotonic())
            self._frame_times = self._frame_times[-30:]
            self._rerender()
            if self._recording is not None:
                self._recording.append(frame)
            self._update_fps()
        except Exception as exc:
            if isinstance(self._source, LeptonSource):
                if isinstance(exc, LeptonFrameTimeout):
                    self._camera_failure_count += 1
                    if self._camera_failure_count < 3:
                        self.source_detail_value.setText(
                            "Frame synchronization lost; resynchronizing "
                            f"({self._camera_failure_count}/3)"
                        )
                        return
                self._finish_recording()
                self._show_camera_unavailable(f"Camera connection lost: {exc}")
            else:
                self._timer.stop()
                self._finish_recording()
                QMessageBox.critical(self, "Frame acquisition failed", str(exc))

    def _update_fps(self) -> None:
        if len(self._frame_times) < 2:
            self.fps_value.setText("—")
            return
        elapsed = self._frame_times[-1] - self._frame_times[0]
        fps = (len(self._frame_times) - 1) / elapsed if elapsed else 0.0
        self.fps_value.setText(f"{fps:.2f} FPS")

    def _display_range(self) -> Tuple[Optional[float], Optional[float]]:
        if self.auto_range_toggle.isChecked():
            return None, None
        minimum_c = self.display_minimum_spin.value()
        maximum_c = max(minimum_c + 0.01, self.display_maximum_spin.value())
        return minimum_c, maximum_c

    def _change_automatic_range(self, automatic: bool) -> None:
        if not automatic and self._current_frame is not None:
            stats = self._current_frame.statistics()
            self.display_minimum_spin.setValue(stats.minimum_c)
            self.display_maximum_spin.setValue(
                max(stats.minimum_c + 0.01, stats.maximum_c)
            )
        locked = self._recording is not None and self.video_mp4_toggle.isChecked()
        self.display_minimum_spin.setEnabled(not automatic and not locked)
        self.display_maximum_spin.setEnabled(not automatic and not locked)
        self._rerender()

    def _change_manual_range(self, _value: float) -> None:
        if self.display_maximum_spin.value() <= self.display_minimum_spin.value():
            self.display_maximum_spin.blockSignals(True)
            self.display_maximum_spin.setValue(
                self.display_minimum_spin.value() + 0.01
            )
            self.display_maximum_spin.blockSignals(False)
        self._rerender()

    def _rerender(self) -> None:
        if self._current_frame is None:
            return
        minimum_c, maximum_c = self._display_range()
        rgb = render_frame(
            self._current_frame,
            palette=self.palette_combo.currentText(),
            minimum_c=minimum_c,
            maximum_c=maximum_c,
        )
        self.canvas.set_frame(self._current_frame, rgb)

    def _capture_still(self) -> None:
        if self._current_frame is None:
            return
        selected = {
            "png": self.still_png_toggle.isChecked(),
            "tiff": self.still_tiff_toggle.isChecked(),
            "npy": self.still_numpy_toggle.isChecked(),
            "json": self.still_metadata_toggle.isChecked(),
        }
        if not any(selected.values()):
            QMessageBox.warning(
                self,
                "No still file type selected",
                "Select at least one file type.",
            )
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose capture location", str(Path.cwd())
        )
        if not chosen:
            return
        minimum_c, maximum_c = self._display_range()
        try:
            preview = (
                render_visual_export(
                    self._current_frame,
                    palette=self.palette_combo.currentText(),
                    show_extrema=False,
                    minimum_c=minimum_c,
                    maximum_c=maximum_c,
                )
                if selected["png"]
                else None
            )
            destination = save_still(
                self._current_frame,
                Path(chosen),
                preview_rgb=preview,
                save_png=selected["png"],
                save_tiff=selected["tiff"],
                save_numpy=selected["npy"],
                save_metadata=selected["json"],
                preview_palette=self.palette_combo.currentText(),
                preview_show_extrema=False,
                display_settings={
                    "automatic_range": self.auto_range_toggle.isChecked(),
                    "minimum_c": minimum_c,
                    "maximum_c": maximum_c,
                },
            )
        except Exception as exc:
            QMessageBox.critical(self, "Capture failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {destination}", 8000)

    def _toggle_recording(self) -> None:
        if self._recording is not None:
            self._finish_recording(show_status=True)
            return
        if self._current_frame is None:
            return
        save_hdf5 = self.video_hdf5_toggle.isChecked()
        save_mp4 = self.video_mp4_toggle.isChecked()
        if not save_hdf5 and not save_mp4:
            QMessageBox.warning(
                self,
                "No video file type selected",
                "Select HDF5, MP4, or both.",
            )
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose recording location", str(Path.cwd())
        )
        if not chosen:
            return
        capture_name = datetime.now().strftime("capture_video_%Y-%m-%d_%H%M%S_%f")
        destination = Path(chosen) / capture_name
        try:
            destination.mkdir(parents=False, exist_ok=False)
            minimum_c, maximum_c = self._display_range()
            self._recording = RadiometricRecordingSession(
                destination / f"{capture_name}.h5" if save_hdf5 else None,
                destination / f"{capture_name}.mp4" if save_mp4 else None,
                self._current_frame,
                palette=self.palette_combo.currentText(),
                fps=self._source.nominal_fps,
                show_extrema=False,
                automatic_range=self.auto_range_toggle.isChecked(),
                minimum_c=minimum_c,
                maximum_c=maximum_c,
            )
            self._recording.append(self._current_frame)
        except Exception as exc:
            recording = self._recording
            self._recording = None
            if recording is not None:
                try:
                    recording.close()
                except Exception:
                    pass
            try:
                destination.rmdir()
            except OSError:
                pass
            QMessageBox.critical(self, "Recording failed", str(exc))
            return
        self.record_button.setText("Stop recording")
        self.video_hdf5_toggle.setEnabled(False)
        self.video_mp4_toggle.setEnabled(False)
        if save_mp4:
            self.palette_combo.setEnabled(False)
            self.auto_range_toggle.setEnabled(False)
            self.display_minimum_spin.setEnabled(False)
            self.display_maximum_spin.setEnabled(False)

    def _finish_recording(self, show_status: bool = False) -> None:
        if self._recording is None:
            return
        recording = self._recording
        self._recording = None
        frame_count = recording.frame_count
        try:
            recording.close()
        except Exception as exc:
            QMessageBox.warning(self, "Recording finalization warning", str(exc))
        self.record_button.setText("Start radiometric recording")
        self.video_hdf5_toggle.setEnabled(True)
        self.video_mp4_toggle.setEnabled(True)
        self.palette_combo.setEnabled(True)
        self.auto_range_toggle.setEnabled(True)
        manual = not self.auto_range_toggle.isChecked()
        self.display_minimum_spin.setEnabled(manual)
        self.display_maximum_spin.setEnabled(manual)
        if show_status:
            self.statusBar().showMessage(
                f"Saved {frame_count} frames to {recording.path.parent.name}", 10000
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self._source.stop()
        self._finish_recording()
        event.accept()
