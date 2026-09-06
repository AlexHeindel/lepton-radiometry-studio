from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from lepton_radiometry_studio.sources import SyntheticSource
from lepton_radiometry_studio.ui.lite_window import LiteMainWindow


def test_lite_window_contains_only_live_capture_controls() -> None:
    application = QApplication.instance() or QApplication([])
    window = LiteMainWindow(auto_connect=False)

    try:
        assert window.windowTitle() == "Lepton Radiometry Lite"
        assert window.centralWidget().layout().count() == 2
        assert window.capture_button.text() == "Capture radiometric still"
        assert window.record_button.text() == "Start radiometric recording"
        assert window.retry_camera_button.isEnabled()
        assert not window.ffc_button.isEnabled()
        assert window.canvas.show_extrema is False
        assert not hasattr(window, "open_still_button")
        assert not hasattr(window, "open_recording_button")
        assert not hasattr(window, "measurements_table")
        assert not hasattr(window, "markers_group")
        assert not hasattr(window, "playback_group")
    finally:
        window.close()
        application.processEvents()


def test_lite_window_captures_stills_and_video(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    window = LiteMainWindow(auto_connect=False)

    try:
        window._start_source(SyntheticSource())
        window._timer.stop()
        assert window._current_frame is not None
        assert window._current_frame._statistics_cache is None
        window.still_png_toggle.setChecked(False)
        window.still_tiff_toggle.setChecked(False)
        window.still_metadata_toggle.setChecked(False)
        window._capture_still()
        still = next(tmp_path.glob("capture_still_*"))
        assert {path.name for path in still.iterdir()} == {"thermal.npy"}

        window.video_mp4_toggle.setChecked(False)
        window._toggle_recording()
        assert window._recording is not None
        video = window._recording.path.parent
        window._acquire_frame()
        window._toggle_recording()
        assert window._recording is None
        assert {path.suffix for path in video.iterdir()} == {".h5"}
    finally:
        window.close()
        application.processEvents()
