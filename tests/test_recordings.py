import numpy as np
import av
import h5py
import pytest

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing import render_frame
from lepton_radiometry_studio.storage.recordings import (
    Hdf5RecordingReader,
    Hdf5RecordingWriter,
    RadiometricRecordingSession,
)


def make_frame(value: int, timestamp: int) -> ThermalFrame:
    return ThermalFrame(
        raw=np.full((3, 4), value, dtype=np.uint16),
        timestamp_ns=timestamp,
        telemetry={"source": "test", "frame_value": value},
        camera_settings={"radiometric": True, "gain_mode": f"mode-{value}"},
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
        assert actual.telemetry == expected.telemetry
        assert actual.camera_settings == expected.camera_settings


def test_reader_reports_recording_timing_and_preview_metadata(tmp_path) -> None:
    path = tmp_path / "timed.h5"
    frames = [make_frame(29000 + index, 1_000_000_000 + index * 100_000_000) for index in range(4)]
    with Hdf5RecordingWriter(
        path,
        frames[0],
        nominal_fps=10.0,
        preview_palette="Iron",
        companion_video="timed.mp4",
    ) as writer:
        for frame in frames:
            writer.append(frame)

    with Hdf5RecordingReader(path) as reader:
        assert reader.nominal_fps == 10.0
        assert reader.duration_seconds == 0.3
        assert reader.elapsed_seconds(2) == 0.2
        assert reader.preview_palette == "Iron"
        assert reader.companion_video == "timed.mp4"


def test_recording_session_creates_radiometric_h5_and_playable_mp4(tmp_path) -> None:
    hdf5_path = tmp_path / "paired.h5"
    video_path = tmp_path / "paired.mp4"
    frames = [
        ThermalFrame(
            raw=np.full((120, 160), 29000 + index * 100, dtype=np.uint16),
            timestamp_ns=1_000_000_000 + index * 100_000_000,
            telemetry={"index": index},
        )
        for index in range(6)
    ]
    with RadiometricRecordingSession(
        hdf5_path,
        video_path,
        frames[0],
        palette="Iron",
        fps=10.0,
    ) as recording:
        for frame in frames:
            recording.append(frame, render_frame(frame, "Iron"))

    assert hdf5_path.stat().st_size > 0
    assert video_path.stat().st_size > 0
    with Hdf5RecordingReader(hdf5_path) as reader:
        assert len(reader) == len(frames)
        assert np.array_equal(reader.frame(5).raw, frames[5].raw)
    with av.open(str(video_path)) as container:
        decoded = list(container.decode(video=0))
    assert len(decoded) == len(frames)


def test_version_one_recordings_remain_readable(tmp_path) -> None:
    path = tmp_path / "legacy.h5"
    with h5py.File(path, "w") as legacy:
        legacy.create_dataset(
            "frames", data=np.full((2, 3, 4), 29315, dtype=np.uint16)
        )
        legacy.create_dataset(
            "timestamps_ns", data=np.array([1_000_000_000, 1_200_000_000])
        )
        legacy.attrs["format_version"] = 1
        legacy.attrs["temperature_scale"] = 0.01
        legacy.attrs["temperature_offset"] = -273.15
        legacy.attrs["telemetry"] = '{"source":"legacy"}'
        legacy.attrs["camera_settings"] = '{"radiometric":true}'

    with Hdf5RecordingReader(path) as reader:
        assert len(reader) == 2
        assert reader.nominal_fps == 5.0
        assert reader.frame(1).temperature_at_celsius(0, 0) == pytest.approx(20.0)
        assert reader.frame(1).telemetry["source"] == "legacy"
