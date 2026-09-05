from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
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
    render_visual_export,
)
from lepton_radiometry_studio.sources import (
    FrameSource,
    Hdf5PlaybackSource,
    StillFileSource,
    SyntheticSource,
)
from lepton_radiometry_studio.storage import RadiometricRecordingSession, save_still
from lepton_radiometry_studio.ui.thermal_canvas import ThermalCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lepton Radiometry Studio")
        self.resize(1080, 720)

        self._source: FrameSource = SyntheticSource()
        self._current_frame: Optional[ThermalFrame] = None
        self._current_rgb = None
        self._recording: Optional[RadiometricRecordingSession] = None
        self._frame_times: list[float] = []
        self._unit = TemperatureUnit.CELSIUS
        self._recording_locks_display = False

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
        self.fps_label = QLabel("Frame rate")
        self.fps_value = QLabel("—")
        source_layout.addRow(self.fps_label, self.fps_value)
        sidebar.addWidget(source_group)

        saved_files_group = QGroupBox("Analyze saved files")
        saved_files_layout = QVBoxLayout(saved_files_group)
        self.open_recording_button = QPushButton("Open .h5 video for analysis…")
        self.open_recording_button.setToolTip(
            "Open a radiometric HDF5 recording in the thermal viewer"
        )
        self.open_recording_button.clicked.connect(self._open_recording)
        saved_files_layout.addWidget(self.open_recording_button)
        self.open_still_button = QPushButton("Open radiometric still for analysis…")
        self.open_still_button.setToolTip(
            "Select preview.png, thermal.npy, or thermal.tiff from a capture_still folder"
        )
        self.open_still_button.clicked.connect(self._open_still)
        saved_files_layout.addWidget(self.open_still_button)
        sidebar.addWidget(saved_files_group)

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
        self.extrema_toggle = QCheckBox("Show min/max markers")
        self.extrema_toggle.setChecked(True)
        self.extrema_toggle.toggled.connect(self.canvas.set_show_extrema)
        display_layout.addRow(self.extrema_toggle)
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

        self.playback_group = QGroupBox("Radiometric playback")
        playback_layout = QVBoxLayout(self.playback_group)
        self.playback_button = QPushButton("Play")
        self.playback_button.clicked.connect(self._toggle_playback)
        playback_layout.addWidget(self.playback_button)
        self.playback_slider = QSlider(Qt.Orientation.Horizontal)
        self.playback_slider.setRange(0, 0)
        self.playback_slider.sliderPressed.connect(self._pause_playback)
        self.playback_slider.valueChanged.connect(self._seek_recording)
        playback_layout.addWidget(self.playback_slider)
        self.playback_value = QLabel("—")
        self.playback_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        playback_layout.addWidget(self.playback_value)
        self.playback_group.setVisible(False)
        sidebar.addWidget(self.playback_group)

        self.capture_button = QPushButton("Capture radiometric still")
        self.capture_button.clicked.connect(self._capture_still)
        sidebar.addWidget(self.capture_button)
        still_types = QHBoxLayout()
        still_types.setContentsMargins(0, 0, 0, 0)
        self.still_png_toggle = QCheckBox("PNG")
        self.still_tiff_toggle = QCheckBox("TIFF")
        self.still_numpy_toggle = QCheckBox("NPY")
        self.still_metadata_toggle = QCheckBox("JSON")
        self.still_png_toggle.setToolTip("Visual preview using the current display settings")
        self.still_tiff_toggle.setToolTip("Original 16-bit radiometric pixel values")
        self.still_numpy_toggle.setToolTip("Original uint16 radiometric array")
        self.still_metadata_toggle.setToolTip(
            "Temperature conversion, telemetry, and display metadata"
        )
        for toggle in (
            self.still_png_toggle,
            self.still_tiff_toggle,
            self.still_numpy_toggle,
            self.still_metadata_toggle,
        ):
            toggle.setChecked(True)
            still_types.addWidget(toggle)
        sidebar.addLayout(still_types)
        self.record_button = QPushButton("Start radiometric recording")
        self.record_button.clicked.connect(self._toggle_recording)
        sidebar.addWidget(self.record_button)
        video_types = QHBoxLayout()
        video_types.setContentsMargins(0, 0, 0, 0)
        self.video_hdf5_toggle = QCheckBox("HDF5")
        self.video_mp4_toggle = QCheckBox("MP4")
        self.video_hdf5_toggle.setToolTip(
            "Radiometric frames, timestamps, and per-frame metadata"
        )
        self.video_mp4_toggle.setToolTip(
            "Visual-only video using the current display settings"
        )
        self.video_hdf5_toggle.setChecked(True)
        self.video_mp4_toggle.setChecked(True)
        video_types.addWidget(self.video_hdf5_toggle)
        video_types.addWidget(self.video_mp4_toggle)
        video_types.addStretch(1)
        sidebar.addLayout(video_types)
        self.synthetic_button = QPushButton("Return to synthetic camera")
        self.synthetic_button.clicked.connect(lambda: self._start_source(SyntheticSource()))
        sidebar.addWidget(self.synthetic_button)
        root.addLayout(sidebar)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Synthetic camera connected")

    def _build_menu(self) -> None:
        # Keep Python references to the menu and actions. On macOS, the native menu
        # can otherwise outlive its temporary PySide wrappers and become disabled.
        self.file_menu = self.menuBar().addMenu("File")
        self.open_action = QAction("Open radiometric still…", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self._open_still)
        self.file_menu.addAction(self.open_action)
        self.open_recording_action = QAction("Open radiometric recording…", self)
        self.open_recording_action.setShortcut("Ctrl+Shift+O")
        self.open_recording_action.triggered.connect(self._open_recording)
        self.file_menu.addAction(self.open_recording_action)
        self.capture_action = QAction("Capture still", self)
        self.capture_action.setShortcut("Ctrl+S")
        self.capture_action.triggered.connect(self._capture_still)
        self.file_menu.addAction(self.capture_action)
        self.file_menu.addSeparator()
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.quit_action)

    def _start_source(self, source: FrameSource) -> None:
        self._finish_recording()
        self._timer.stop() if hasattr(self, "_timer") else None
        self._source.stop()
        self._source = source
        self._source.start()
        self.source_value.setText(source.name)
        self._frame_times.clear()
        interval_ms = max(1, round(1000.0 / source.nominal_fps))
        self._timer.start(interval_ms)
        is_playback = isinstance(source, Hdf5PlaybackSource)
        is_still = isinstance(source, StillFileSource)
        self.fps_label.setVisible(not is_still)
        self.fps_value.setVisible(not is_still)
        self.playback_group.setVisible(is_playback)
        self.record_button.setEnabled(not is_playback)
        if is_playback:
            self.playback_slider.setRange(0, source.frame_count - 1)
            self.playback_slider.setValue(0)
            self.playback_button.setText("Play")
        self._acquire_frame()
        if is_playback and not source.is_playing:
            self._timer.stop()
        self.statusBar().showMessage(f"Connected to {source.name}", 4000)

    def _acquire_frame(self) -> None:
        try:
            frame = self._source.next_frame()
            self._current_frame = frame
            self._frame_times.append(time.monotonic())
            self._frame_times = self._frame_times[-30:]
            self._rerender()
            if self._recording is not None:
                self._recording.append(frame)
            self._update_measurements()
            self._update_fps()
            self._update_playback_controls()
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
        if isinstance(self._source, StillFileSource):
            return
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
        save_png = self.still_png_toggle.isChecked()
        save_tiff = self.still_tiff_toggle.isChecked()
        save_numpy = self.still_numpy_toggle.isChecked()
        save_metadata = self.still_metadata_toggle.isChecked()
        if not any((save_png, save_tiff, save_numpy, save_metadata)):
            QMessageBox.warning(
                self, "No still file type selected", "Select at least one file type."
            )
            return
        chosen = QFileDialog.getExistingDirectory(self, "Choose capture location", str(Path.cwd()))
        if not chosen:
            return
        try:
            preview_rgb = (
                render_visual_export(
                    self._current_frame,
                    palette=self.palette_combo.currentText(),
                    show_extrema=self.extrema_toggle.isChecked(),
                )
                if save_png
                else None
            )
            destination = save_still(
                self._current_frame,
                Path(chosen),
                preview_rgb=preview_rgb,
                save_png=save_png,
                save_tiff=save_tiff,
                save_numpy=save_numpy,
                save_metadata=save_metadata,
                preview_palette=self.palette_combo.currentText(),
                preview_show_extrema=self.extrema_toggle.isChecked(),
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
            "Radiometric captures (*.png *.npy *.tif *.tiff *.json);;All files (*)",
        )
        if not path:
            return
        try:
            self._start_source(StillFileSource(Path(path)))
        except Exception as exc:
            QMessageBox.critical(self, "Could not open still", str(exc))

    def _open_recording(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open radiometric recording",
            str(Path.cwd()),
            "Lepton radiometric recordings (*.h5 *.hdf5);;All files (*)",
        )
        if not path:
            return
        try:
            self._start_source(Hdf5PlaybackSource(Path(path)))
        except Exception as exc:
            QMessageBox.critical(self, "Could not open recording", str(exc))

    def _toggle_playback(self) -> None:
        if not isinstance(self._source, Hdf5PlaybackSource):
            return
        if self._source.is_playing:
            self._pause_playback()
            return
        self._source.play()
        self.playback_button.setText("Pause")
        interval_ms = max(1, round(1000.0 / self._source.nominal_fps))
        self._timer.start(interval_ms)

    def _pause_playback(self) -> None:
        if not isinstance(self._source, Hdf5PlaybackSource):
            return
        self._source.pause()
        self._timer.stop()
        self.playback_button.setText("Play")

    def _seek_recording(self, index: int) -> None:
        if not isinstance(self._source, Hdf5PlaybackSource):
            return
        self._source.seek(index)
        self.playback_button.setText("Play")
        self._timer.stop()
        self._acquire_frame()

    def _update_playback_controls(self) -> None:
        if not isinstance(self._source, Hdf5PlaybackSource):
            return
        index = self._source.current_index
        self.playback_slider.blockSignals(True)
        self.playback_slider.setValue(index)
        self.playback_slider.blockSignals(False)
        elapsed = self._source.elapsed_seconds
        duration = self._source.duration_seconds
        if duration <= 0 and self._source.frame_count > 1:
            duration = (self._source.frame_count - 1) / self._source.nominal_fps
        self.playback_value.setText(
            f"Frame {index + 1} / {self._source.frame_count}  ·  "
            f"{elapsed:.1f} / {duration:.1f} s"
        )
        if not self._source.is_playing:
            self._timer.stop()
            self.playback_button.setText("Play")

    def _toggle_recording(self) -> None:
        if self._recording is not None:
            self._finish_recording(show_status=True)
            return
        if self._current_frame is None:
            return
        save_hdf5 = self.video_hdf5_toggle.isChecked()
        save_mp4 = self.video_mp4_toggle.isChecked()
        if not any((save_hdf5, save_mp4)):
            QMessageBox.warning(
                self, "No video file type selected", "Select HDF5, MP4, or both."
            )
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose recording location", str(Path.cwd())
        )
        if not chosen:
            return
        capture_name = datetime.now().strftime(
            "capture_video_%Y-%m-%d_%H%M%S_%f"
        )
        destination = Path(chosen) / capture_name
        try:
            destination.mkdir(parents=False, exist_ok=False)
        except Exception as exc:
            QMessageBox.critical(self, "Recording failed", str(exc))
            return
        hdf5_path = destination / f"{capture_name}.h5" if save_hdf5 else None
        video_path = destination / f"{capture_name}.mp4" if save_mp4 else None
        palette = self.palette_combo.currentText()
        try:
            self._recording = RadiometricRecordingSession(
                hdf5_path,
                video_path,
                self._current_frame,
                palette=palette,
                fps=self._source.nominal_fps,
                show_extrema=self.extrema_toggle.isChecked(),
            )
            self._recording.append(self._current_frame)
        except Exception as exc:
            if self._recording is not None:
                try:
                    self._recording.close()
                except Exception:
                    pass
                self._recording = None
            try:
                destination.rmdir()
            except OSError:
                # Preserve a non-empty folder if either writer produced useful data.
                pass
            QMessageBox.critical(self, "Recording failed", str(exc))
            return
        self.record_button.setText("Stop recording")
        self.video_hdf5_toggle.setEnabled(False)
        self.video_mp4_toggle.setEnabled(False)
        self._recording_locks_display = save_mp4
        if self._recording_locks_display:
            self.palette_combo.setEnabled(False)
            self.extrema_toggle.setEnabled(False)
        formats = " + ".join(
            name for name, selected in (("HDF5", save_hdf5), ("MP4", save_mp4)) if selected
        )
        self.statusBar().showMessage(
            f"Recording {formats} with {palette} display", 5000
        )

    def _finish_recording(self, show_status: bool = False) -> None:
        if self._recording is None:
            return
        recording = self._recording
        self._recording = None
        frame_count = recording.frame_count
        try:
            recording.close()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Recording finalization warning",
                f"One or more recording files could not be finalized:\n{exc}",
            )
        self.record_button.setText("Start radiometric recording")
        self.video_hdf5_toggle.setEnabled(True)
        self.video_mp4_toggle.setEnabled(True)
        if self._recording_locks_display:
            self.palette_combo.setEnabled(True)
            self.extrema_toggle.setEnabled(True)
            self._recording_locks_display = False
        if show_status:
            self.statusBar().showMessage(
                f"Saved {frame_count} frames to {recording.path.parent.name}",
                10000,
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self._source.stop()
        self._finish_recording()
        event.accept()
