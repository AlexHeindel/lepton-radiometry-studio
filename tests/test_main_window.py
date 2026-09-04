from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QApplication

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources import Hdf5PlaybackSource
from lepton_radiometry_studio.storage import Hdf5RecordingWriter
from lepton_radiometry_studio.ui.main_window import MainWindow


def test_file_menu_actions_remain_available() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()

    try:
        actions = {action.text(): action for action in window.file_menu.actions()}
        assert actions["Open radiometric still…"].isEnabled()
        assert actions["Open radiometric recording…"].isEnabled()
        assert actions["Capture still"].isEnabled()
        assert actions["Quit"].isEnabled()
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

    window = MainWindow()
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
