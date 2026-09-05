from __future__ import annotations

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing import render_visual_export
from lepton_radiometry_studio.sources import (
    Hdf5PlaybackSource,
    StillFileSource,
    SyntheticSource,
)
from lepton_radiometry_studio.storage import Hdf5RecordingWriter, save_still
from lepton_radiometry_studio.ui.main_window import MainWindow


def test_file_menu_actions_remain_available() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_connect=False)

    try:
        actions = {action.text(): action for action in window.file_menu.actions()}
        assert actions["Open radiometric still…"].isEnabled()
        assert actions["Open radiometric recording…"].isEnabled()
        assert not actions["Capture still"].isEnabled()
        assert actions["Quit"].isEnabled()
        assert window.open_recording_button.isEnabled()
        assert window.open_still_button.isEnabled()
        assert window.retry_camera_button.isEnabled()
        assert window.synthetic_button.isEnabled()
        assert window.source_value.text() == "Camera not found"
        assert window.canvas.empty_message.startswith("Camera not found")
        assert window.extrema_toggle.isChecked()
        assert window.auto_range_toggle.isChecked()
        assert not window.display_minimum_spin.isEnabled()
        assert not window.display_maximum_spin.isEnabled()
        assert window.still_png_toggle.isChecked()
        assert window.still_tiff_toggle.isChecked()
        assert window.still_numpy_toggle.isChecked()
        assert window.still_metadata_toggle.isChecked()
        assert window.video_hdf5_toggle.isChecked()
        assert window.video_mp4_toggle.isChecked()
    finally:
        window.close()
        application.processEvents()


def test_synthetic_camera_is_an_explicit_demo_choice() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_connect=False)

    try:
        assert window._current_frame is None
        window.synthetic_button.click()
        window._timer.stop()

        assert isinstance(window._source, SyntheticSource)
        assert window._current_frame is not None
        assert window.source_detail_value.text() == "Demo data; no camera hardware"
    finally:
        window.close()
        application.processEvents()


def test_manual_display_range_does_not_change_radiometric_frame() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        assert window._current_frame is not None
        original_raw = window._current_frame.raw.copy()
        window.auto_range_toggle.setChecked(False)
        window.display_minimum_spin.setValue(18.0)
        window.display_maximum_spin.setValue(24.0)

        assert np.array_equal(window._current_frame.raw, original_raw)
        assert window.display_minimum_spin.isEnabled()
        assert window.display_maximum_spin.isEnabled()
        assert "18.00 to 24.00 °C" == window.range_used_value.text()
    finally:
        window.close()
        application.processEvents()


def test_persistent_point_and_roi_readouts_update() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        window.canvas.add_point_marker(10, 10)
        window.canvas.add_region("rectangle", 10, 10, 20, 20)

        summary = window.saved_measurements_value.text()
        assert "P1 (10, 10)" in summary
        assert "R1 · 121 px" in summary
        assert "min" in summary and "max" in summary and "avg" in summary
    finally:
        window.close()
        application.processEvents()


def test_recording_uses_self_contained_capture_video_folder(
    tmp_path, monkeypatch
) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        window._toggle_recording()
        assert window._recording is not None
        destination = window._recording.path.parent
        assert destination.name.startswith("capture_video_")
        assert window._recording.path.stem == destination.name
        assert window._recording.video_path is not None
        assert window._recording.video_path.stem == destination.name

        window._toggle_recording()

        assert window._recording is None
        assert (destination / f"{destination.name}.h5").exists()
        assert (destination / f"{destination.name}.mp4").exists()
    finally:
        window.close()
        application.processEvents()


def test_video_type_toggles_can_save_hdf5_only(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        window.video_mp4_toggle.setChecked(False)
        window._toggle_recording()
        assert window._recording is not None
        destination = window._recording.path.parent
        window._toggle_recording()

        assert {path.suffix for path in destination.iterdir()} == {".h5"}
    finally:
        window.close()
        application.processEvents()


def test_still_type_toggles_can_save_display_matched_png_only(
    tmp_path, monkeypatch
) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        window.palette_combo.setCurrentText("Grayscale")
        window.extrema_toggle.setChecked(False)
        window.still_tiff_toggle.setChecked(False)
        window.still_numpy_toggle.setChecked(False)
        window.still_metadata_toggle.setChecked(False)
        assert window._current_frame is not None
        expected = render_visual_export(
            window._current_frame,
            palette="Grayscale",
            show_extrema=False,
        )

        window._capture_still()

        destination = next(tmp_path.glob("capture_still_*"))
        assert {path.name for path in destination.iterdir()} == {"preview.png"}
        actual = np.asarray(Image.open(destination / "preview.png"))
        assert np.array_equal(actual, expected)
    finally:
        window.close()
        application.processEvents()


def test_still_source_hides_frame_rate(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    frame = ThermalFrame(
        raw=np.full((2, 3), 29315, dtype=np.uint16),
        timestamp_ns=1,
    )
    destination = save_still(
        frame,
        tmp_path,
        preview_rgb=np.zeros((8, 12, 3), dtype=np.uint8),
    )
    window = MainWindow(auto_connect=False)

    try:
        window._start_source(StillFileSource(destination / "preview.png"))
        assert window.fps_label.isHidden()
        assert window.fps_value.isHidden()
    finally:
        window.close()
        application.processEvents()


def test_playback_slider_seeks_recording(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "seekable.h5"
    frames = [
        ThermalFrame(
            raw=np.full((2, 3), 29000 + index, dtype=np.uint16),
            timestamp_ns=1_000_000_000 + index * 200_000_000,
        )
        for index in range(3)
    ]
    with Hdf5RecordingWriter(path, frames[0], nominal_fps=5.0) as writer:
        for frame in frames:
            writer.append(frame)

    window = MainWindow(auto_connect=False)
    try:
        window._start_source(Hdf5PlaybackSource(path))
        window.playback_slider.setValue(2)

        assert window._source.current_index == 2
        assert window._current_frame is not None
        assert window._current_frame.raw_at(0, 0) == 29002
        assert window.playback_value.text().startswith("Frame 3 / 3")
    finally:
        window.close()
        application.processEvents()
