import numpy as np

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.recording import Hdf5PlaybackSource
from lepton_radiometry_studio.storage import Hdf5RecordingWriter


def make_recording(path) -> None:
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


def test_playback_can_play_pause_seek_and_restart(tmp_path) -> None:
    path = tmp_path / "playback.h5"
    make_recording(path)
    source = Hdf5PlaybackSource(path)
    try:
        assert source.frame_count == 3
        assert source.nominal_fps == 5.0
        assert source.next_frame().raw_at(0, 0) == 29000
        assert source.current_index == 0

        source.play()
        assert source.next_frame().raw_at(0, 0) == 29001
        assert source.next_frame().raw_at(0, 0) == 29002
        assert source.is_playing is False

        source.seek(1)
        assert source.next_frame().raw_at(0, 0) == 29001
        source.play()
        source.pause()
        assert source.next_frame().raw_at(0, 0) == 29001

        source.seek(2)
        source.next_frame()
        source.play()
        assert source.next_frame().raw_at(0, 0) == 29000
    finally:
        source.stop()
