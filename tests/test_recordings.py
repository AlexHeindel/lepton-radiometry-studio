import numpy as np
import av
import h5py
import pytest

from lepton_radiometry_studio.domain import PointMarker, RegionOfInterest, ThermalFrame
from lepton_radiometry_studio.processing import render_visual_export
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
        preview_show_extrema=False,
        companion_video="timed.mp4",
    ) as writer:
        for frame in frames:
            writer.append(frame)

    with Hdf5RecordingReader(path) as reader:
        assert reader.nominal_fps == 10.0
        assert reader.duration_seconds == 0.3
        assert reader.elapsed_seconds(2) == 0.2
        assert reader.preview_palette == "Iron"
        assert reader.preview_show_extrema is False
        assert reader.companion_video == "timed.mp4"


def test_recording_saves_display_range_and_measurement_recipe(tmp_path) -> None:
    path = tmp_path / "display-settings.h5"
    frame = make_frame(29000, 1)
    with RadiometricRecordingSession(
        path,
        None,
        frame,
        palette="Rainbow",
        fps=8.7,
        show_extrema=False,
        automatic_range=False,
        minimum_c=10.0,
        maximum_c=40.0,
        point_markers=[PointMarker(1, 2, 1)],
        regions=[RegionOfInterest(1, "rectangle", 0, 0, 2, 2)],
    ) as recording:
        recording.append(frame)

    with Hdf5RecordingReader(path) as reader:
        settings = reader.display_settings
        assert settings["palette"] == "Rainbow"
        assert settings["show_extrema"] is False
        assert settings["automatic_range"] is False
        assert settings["minimum_c"] == 10.0
        assert settings["maximum_c"] == 40.0
        assert settings["point_markers"] == [{"id": 1, "x": 2, "y": 1}]
        assert settings["regions"][0]["kind"] == "rectangle"


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
        automatic_range=False,
        minimum_c=15.0,
        maximum_c=25.0,
    ) as recording:
        for frame in frames:
            recording.append(frame)

    assert hdf5_path.stat().st_size > 0
    assert video_path.stat().st_size > 0
    assert recording.frame_count == len(frames)
    with Hdf5RecordingReader(hdf5_path) as reader:
        assert len(reader) == len(frames)
        assert np.array_equal(reader.frame(5).raw, frames[5].raw)
        assert reader.display_settings["automatic_range"] is False
        assert reader.display_settings["minimum_c"] == 15.0
        assert reader.display_settings["maximum_c"] == 25.0
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        decoded = list(container.decode(video=0))
    assert stream.codec_context.name in {"h264", "mpeg4"}
    assert (stream.width, stream.height) == (640, 480)
    assert len(decoded) == len(frames)
    first_rgb = decoded[0].to_ndarray(format="rgb24")
    expected_rgb = render_visual_export(
        frames[0],
        "Iron",
        show_extrema=True,
        minimum_c=15.0,
        maximum_c=25.0,
    )
    assert np.mean(np.abs(first_rgb.astype(float) - expected_rgb.astype(float))) < 4.0


@pytest.mark.parametrize(
    "save_hdf5,save_mp4",
    [(True, False), (False, True)],
)
def test_recording_session_supports_individual_file_types(
    tmp_path, save_hdf5: bool, save_mp4: bool
) -> None:
    frame = ThermalFrame(
        raw=np.full((120, 160), 29315, dtype=np.uint16),
        timestamp_ns=1,
    )
    hdf5_path = tmp_path / "only.h5" if save_hdf5 else None
    video_path = tmp_path / "only.mp4" if save_mp4 else None

    with RadiometricRecordingSession(
        hdf5_path,
        video_path,
        frame,
        palette="Grayscale",
        fps=8.7,
        show_extrema=False,
    ) as recording:
        recording.append(frame)

    assert (tmp_path / "only.h5").exists() is save_hdf5
    assert (tmp_path / "only.mp4").exists() is save_mp4
    assert recording.frame_count == 1


def test_writer_frame_count_remains_available_after_close(tmp_path) -> None:
    path = tmp_path / "closed.h5"
    frame = make_frame(29000, 100)
    writer = Hdf5RecordingWriter(path, frame)
    writer.append(frame)
    writer.close()

    assert writer.frame_count == 1


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
