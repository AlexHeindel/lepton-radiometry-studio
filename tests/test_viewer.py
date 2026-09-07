from __future__ import annotations

import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

from lepton_radiometry_studio.sources.lepton import LeptonFrameTimeout
from lepton_radiometry_studio.ui.feed_window import FeedCanvas, FeedWindow
from lepton_radiometry_studio.viewer import build_parser


def test_viewer_cli_defaults_to_iron_camera_feed() -> None:
    args = build_parser().parse_args([])

    assert args.palette == "Iron"
    assert args.source == "camera"
    assert args.fullscreen is False


def test_viewer_cli_validates_palette() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--palette", "not-a-palette"])

    assert exc_info.value.code == 2


def test_importing_viewer_cli_does_not_load_qt_or_recording_libraries() -> None:
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from lepton_radiometry_studio.viewer import main; "
                "assert 'PySide6' not in sys.modules; "
                "assert 'h5py' not in sys.modules; "
                "assert 'av' not in sys.modules; "
                "assert 'PIL' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_feed_window_import_does_not_load_capture_or_recording_stack() -> None:
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import lepton_radiometry_studio.ui.feed_window; "
                "assert 'lepton_radiometry_studio.storage' not in sys.modules; "
                "assert 'h5py' not in sys.modules; "
                "assert 'av' not in sys.modules; "
                "assert 'PIL' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert check.returncode == 0, check.stderr


def test_feed_window_contains_only_the_camera_canvas() -> None:
    application = QApplication.instance() or QApplication([])
    window = FeedWindow(
        palette="Grayscale", source_kind="synthetic", auto_connect=False
    )

    try:
        assert isinstance(window.centralWidget(), FeedCanvas)
        assert window.menuWidget() is None
        assert window.findChildren(QPushButton) == []
        assert window.findChildren(QComboBox) == []
        assert window.findChildren(QLabel) == []
        assert window._frame_timer.timerType() == Qt.TimerType.PreciseTimer

        window._connect_source()
        window._frame_timer.stop()
        assert window.canvas.has_image
        assert window._source is not None
    finally:
        window.close()
        application.processEvents()


def test_feed_window_reconnects_after_repeated_timeouts() -> None:
    application = QApplication.instance() or QApplication([])
    window = FeedWindow(auto_connect=False)

    class TimeoutSource:
        nominal_fps = 8.7
        stopped = False

        def next_frame(self):
            raise LeptonFrameTimeout("lost sync")

        def stop(self) -> None:
            self.stopped = True

    source = TimeoutSource()
    window._source = source
    try:
        for _ in range(5):
            window._acquire_frame()

        assert source.stopped
        assert window._source is None
        assert window._reconnect_timer.isActive()
    finally:
        window.close()
        application.processEvents()
