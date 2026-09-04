import numpy as np

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.storage.recordings import (
    Hdf5RecordingReader,
    Hdf5RecordingWriter,
)


def make_frame(value: int, timestamp: int) -> ThermalFrame:
    return ThermalFrame(
        raw=np.full((3, 4), value, dtype=np.uint16),
        timestamp_ns=timestamp,
        telemetry={"source": "test"},
        camera_settings={"radiometric": True},
    )


def test_recording_round_trip(tmp_path) -> None:
    path = tmp_path / "recording.h5"
    frames = [make_frame(29000 + index, 100 + index) for index in range(3)]
    with Hdf5RecordingWriter(path, frames[0]) as writer:
        for frame in frames:
            writer.append(frame)
        assert writer.frame_count == 3

    with Hdf5RecordingReader(path) as reader:
        loaded = list(reader.frames())

    assert len(loaded) == 3
    for actual, expected in zip(loaded, frames):
        assert np.array_equal(actual.raw, expected.raw)
        assert actual.timestamp_ns == expected.timestamp_ns

