from __future__ import annotations

import json
import queue
import threading
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

import av
import h5py
import numpy as np

from lepton_radiometry_studio.domain import (
    PointMarker,
    RegionOfInterest,
    ThermalFrame,
)
from lepton_radiometry_studio.processing import render_visual_export


class Hdf5RecordingWriter:
    """Append-only radiometric recording with explicit frame timestamps."""

    def __init__(
        self,
        path: Path,
        first_frame: ThermalFrame,
        nominal_fps: float = 8.7,
        preview_palette: Optional[str] = None,
        preview_show_extrema: Optional[bool] = None,
        companion_video: Optional[str] = None,
        display_settings: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = h5py.File(self.path, "w")
        self._frames = self._file.create_dataset(
            "frames",
            shape=(0, *first_frame.shape),
            maxshape=(None, *first_frame.shape),
            chunks=(1, *first_frame.shape),
            compression="gzip",
            compression_opts=4,
            dtype=np.uint16,
        )
        self._timestamps = self._file.create_dataset(
            "timestamps_ns",
            shape=(0,),
            maxshape=(None,),
            chunks=(256,),
            dtype=np.uint64,
        )
        self._scales = self._file.create_dataset(
            "temperature_scales",
            shape=(0,),
            maxshape=(None,),
            chunks=(256,),
            dtype=np.float64,
        )
        self._offsets = self._file.create_dataset(
            "temperature_offsets",
            shape=(0,),
            maxshape=(None,),
            chunks=(256,),
            dtype=np.float64,
        )
        string_type = h5py.string_dtype(encoding="utf-8")
        self._telemetry = self._file.create_dataset(
            "telemetry_json",
            shape=(0,),
            maxshape=(None,),
            chunks=(256,),
            dtype=string_type,
        )
        self._camera_settings = self._file.create_dataset(
            "camera_settings_json",
            shape=(0,),
            maxshape=(None,),
            chunks=(256,),
            dtype=string_type,
        )
        self._file.attrs["format_version"] = 2
        self._file.attrs["temperature_scale"] = first_frame.temperature_scale
        self._file.attrs["temperature_offset"] = first_frame.temperature_offset
        self._file.attrs["telemetry"] = json.dumps(dict(first_frame.telemetry))
        self._file.attrs["camera_settings"] = json.dumps(dict(first_frame.camera_settings))
        self._file.attrs["nominal_fps"] = float(nominal_fps)
        if preview_palette is not None:
            self._file.attrs["preview_palette"] = preview_palette
        if preview_show_extrema is not None:
            self._file.attrs["preview_show_extrema"] = bool(preview_show_extrema)
        if companion_video is not None:
            self._file.attrs["companion_video"] = companion_video
        if display_settings is not None:
            self._file.attrs["display_settings_json"] = json.dumps(
                dict(display_settings), default=_json_default, separators=(",", ":")
            )
        self._frame_count = 0
        self._closed = False

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def append(self, frame: ThermalFrame) -> None:
        if self._closed:
            raise RuntimeError("Recording is closed")
        if frame.shape != self._frames.shape[1:]:
            raise ValueError("All recording frames must have the same dimensions")
        index = self.frame_count
        self._frames.resize(index + 1, axis=0)
        self._timestamps.resize(index + 1, axis=0)
        self._scales.resize(index + 1, axis=0)
        self._offsets.resize(index + 1, axis=0)
        self._telemetry.resize(index + 1, axis=0)
        self._camera_settings.resize(index + 1, axis=0)
        self._frames[index] = frame.raw
        self._timestamps[index] = frame.timestamp_ns
        self._scales[index] = frame.temperature_scale
        self._offsets[index] = frame.temperature_offset
        self._telemetry[index] = _to_json(frame.telemetry)
        self._camera_settings[index] = _to_json(frame.camera_settings)
        self._frame_count += 1
        if self._frame_count == 1 or self._frame_count % 16 == 0:
            self._file.flush()

    def close(self) -> None:
        if not self._closed:
            self._file.flush()
            self._file.close()
            self._closed = True

    def __enter__(self) -> "Hdf5RecordingWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Hdf5RecordingReader:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._file = h5py.File(self.path, "r")
        if "frames" not in self._file or "timestamps_ns" not in self._file:
            self._file.close()
            raise ValueError("Not a Lepton Radiometry Studio recording")
        self._frames = self._file["frames"]
        self._timestamps = self._file["timestamps_ns"]
        if self._frames.ndim != 3 or self._frames.dtype != np.uint16:
            self._file.close()
            raise ValueError("Recording frames must be a 3D uint16 dataset")
        if len(self._frames) != len(self._timestamps):
            self._file.close()
            raise ValueError("Recording frame and timestamp counts do not match")

    def __len__(self) -> int:
        return int(self._frames.shape[0])

    @property
    def nominal_fps(self) -> float:
        stored = float(self._file.attrs.get("nominal_fps", 0.0))
        if stored > 0:
            return stored
        sample_count = min(len(self), 1000)
        if sample_count >= 2:
            timestamps = np.asarray(self._timestamps[:sample_count], dtype=np.float64)
            positive_deltas = np.diff(timestamps)
            positive_deltas = positive_deltas[positive_deltas > 0]
            if positive_deltas.size:
                estimated = 1e9 / float(np.median(positive_deltas))
                if 0.1 <= estimated <= 120.0:
                    return estimated
        return 8.7

    @property
    def duration_seconds(self) -> float:
        if len(self) < 2:
            return 0.0
        return max(0.0, (int(self._timestamps[-1]) - int(self._timestamps[0])) / 1e9)

    def elapsed_seconds(self, index: int) -> float:
        if not 0 <= index < len(self):
            raise IndexError(index)
        if len(self) < 2:
            return 0.0
        return max(0.0, (int(self._timestamps[index]) - int(self._timestamps[0])) / 1e9)

    @property
    def preview_palette(self) -> Optional[str]:
        value = self._file.attrs.get("preview_palette")
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @property
    def preview_show_extrema(self) -> Optional[bool]:
        value = self._file.attrs.get("preview_show_extrema")
        return None if value is None else bool(value)

    @property
    def companion_video(self) -> Optional[str]:
        value = self._file.attrs.get("companion_video")
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @property
    def display_settings(self) -> Mapping[str, Any]:
        value = self._file.attrs.get("display_settings_json")
        if value is not None:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            loaded = json.loads(str(value))
            return loaded if isinstance(loaded, dict) else {}
        settings: dict[str, Any] = {}
        if self.preview_palette is not None:
            settings["palette"] = self.preview_palette
        if self.preview_show_extrema is not None:
            settings["show_extrema"] = self.preview_show_extrema
        return settings

    def frame(self, index: int) -> ThermalFrame:
        if not 0 <= index < len(self):
            raise IndexError(index)
        if "temperature_scales" in self._file:
            scale = float(self._file["temperature_scales"][index])
        else:
            scale = float(self._file.attrs["temperature_scale"])
        if "temperature_offsets" in self._file:
            offset = float(self._file["temperature_offsets"][index])
        else:
            offset = float(self._file.attrs["temperature_offset"])
        if "telemetry_json" in self._file:
            telemetry = _from_json(self._file["telemetry_json"][index])
        else:
            telemetry = json.loads(self._file.attrs.get("telemetry", "{}"))
        if "camera_settings_json" in self._file:
            camera_settings = _from_json(self._file["camera_settings_json"][index])
        else:
            camera_settings = json.loads(self._file.attrs.get("camera_settings", "{}"))
        return ThermalFrame(
            raw=np.asarray(self._frames[index], dtype=np.uint16),
            timestamp_ns=int(self._timestamps[index]),
            temperature_scale=scale,
            temperature_offset=offset,
            telemetry=telemetry,
            camera_settings=camera_settings,
        )

    def frames(self) -> Iterator[ThermalFrame]:
        for index in range(len(self)):
            yield self.frame(index)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "Hdf5RecordingReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Mp4VideoWriter:
    """Write a smooth, high-quality visual companion; this is not radiometric data."""

    def __init__(
        self,
        path: Path,
        width: int,
        height: int,
        fps: float,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._source_shape = (height, width, 3)
        rate = Fraction(str(max(0.1, fps))).limit_denominator(1000)
        self._container = av.open(str(self.path), mode="w", format="mp4")
        try:
            self._stream = self._container.add_stream(
                "libx264",
                rate=rate,
                options={"crf": "12", "preset": "medium"},
            )
        except Exception:
            # Keep recording functional on a PyAV build without libx264.
            self._stream = self._container.add_stream("mpeg4", rate=rate)
        self._stream.width = width
        self._stream.height = height
        self._stream.pix_fmt = "yuv420p"
        self._closed = False
        self._frame_count = 0

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def append(self, rgb: np.ndarray) -> None:
        if self._closed:
            raise RuntimeError("Video is closed")
        image = np.ascontiguousarray(rgb, dtype=np.uint8)
        if image.shape != self._source_shape:
            raise ValueError(f"Video frame must have shape {self._source_shape}")
        frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        for packet in self._stream.encode(frame):
            self._container.mux(packet)
        self._frame_count += 1

    def close(self) -> None:
        if self._closed:
            return
        for packet in self._stream.encode():
            self._container.mux(packet)
        self._container.close()
        self._closed = True

    def __enter__(self) -> "Mp4VideoWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class RadiometricRecordingSession:
    """Write selected measurement-grade HDF5 and visual MP4 outputs."""

    def __init__(
        self,
        hdf5_path: Optional[Path],
        video_path: Optional[Path],
        first_frame: ThermalFrame,
        palette: str,
        fps: float,
        show_extrema: bool = True,
        automatic_range: bool = True,
        minimum_c: Optional[float] = None,
        maximum_c: Optional[float] = None,
        point_markers: Sequence[PointMarker] = (),
        regions: Sequence[RegionOfInterest] = (),
    ) -> None:
        if hdf5_path is None and video_path is None:
            raise ValueError("Select at least one video file type")
        if not automatic_range:
            if minimum_c is None or maximum_c is None:
                raise ValueError("A fixed display range requires minimum and maximum")
            if not np.isfinite(minimum_c) or not np.isfinite(maximum_c):
                raise ValueError("Display range must be finite")
            if maximum_c <= minimum_c:
                raise ValueError("Display maximum must be greater than minimum")
        self.hdf5_path = Path(hdf5_path) if hdf5_path is not None else None
        self.video_path = Path(video_path) if video_path is not None else None
        self.path = self.hdf5_path or self.video_path
        assert self.path is not None
        self.palette = palette
        self.show_extrema = show_extrema
        self.automatic_range = automatic_range
        self.minimum_c = None if automatic_range else minimum_c
        self.maximum_c = None if automatic_range else maximum_c
        self.point_markers = tuple(point_markers)
        self.regions = tuple(regions)
        display_settings = {
            "palette": palette,
            "show_extrema": bool(show_extrema),
            "automatic_range": bool(automatic_range),
            "minimum_c": minimum_c,
            "maximum_c": maximum_c,
            "point_markers": [marker.to_dict() for marker in self.point_markers],
            "regions": [region.to_dict() for region in self.regions],
        }
        self._hdf5: Optional[Hdf5RecordingWriter] = None
        self._video: Optional[Mp4VideoWriter] = None
        self._frame_count = 0
        try:
            if self.hdf5_path is not None:
                self._hdf5 = Hdf5RecordingWriter(
                    self.hdf5_path,
                    first_frame,
                    nominal_fps=fps,
                    preview_palette=palette,
                    preview_show_extrema=show_extrema,
                    companion_video=(
                        self.video_path.name if self.video_path is not None else None
                    ),
                    display_settings=display_settings,
                )
            if self.video_path is not None:
                self._video = Mp4VideoWriter(
                    self.video_path,
                    first_frame.width * 4,
                    first_frame.height * 4,
                    fps,
                )
        except Exception:
            if self._hdf5 is not None:
                self._hdf5.close()
            if self.hdf5_path is not None:
                self.hdf5_path.unlink(missing_ok=True)
            if self.video_path is not None:
                self.video_path.unlink(missing_ok=True)
            raise
        self._closed = False
        self._worker_error: Optional[Exception] = None
        self._write_queue: queue.Queue[Optional[ThermalFrame]] = queue.Queue(
            maxsize=256
        )
        self._worker = threading.Thread(
            target=self._write_loop,
            name="radiometric-recording-writer",
            daemon=True,
        )
        self._worker.start()

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def append(self, frame: ThermalFrame) -> None:
        if self._closed:
            raise RuntimeError("Recording session is closed")
        if self._worker_error is not None:
            raise RuntimeError("Recording writer failed") from self._worker_error
        try:
            self._write_queue.put_nowait(frame)
        except queue.Full as exc:
            raise RuntimeError("Recording writer could not keep up with capture") from exc
        self._frame_count += 1

    def _write_loop(self) -> None:
        while True:
            frame = self._write_queue.get()
            try:
                if frame is None:
                    return
                if self._worker_error is None:
                    self._append_frame(frame)
            except Exception as exc:
                self._worker_error = exc
            finally:
                self._write_queue.task_done()

    def _append_frame(self, frame: ThermalFrame) -> None:
        if self._hdf5 is not None:
            self._hdf5.append(frame)
        if self._video is not None:
            preview_rgb = render_visual_export(
                frame,
                palette=self.palette,
                show_extrema=self.show_extrema,
                minimum_c=self.minimum_c,
                maximum_c=self.maximum_c,
                point_markers=self.point_markers,
                regions=self.regions,
            )
            self._video.append(preview_rgb)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._write_queue.put(None)
        self._worker.join()
        video_error: Optional[Exception] = None
        try:
            if self._video is not None:
                self._video.close()
        except Exception as exc:
            video_error = exc
        finally:
            if self._hdf5 is not None:
                self._hdf5.close()
        if self._worker_error is not None:
            raise RuntimeError("Recording writer failed") from self._worker_error
        if video_error is not None:
            raise video_error

    def __enter__(self) -> "RadiometricRecordingSession":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _to_json(values: Mapping[str, Any]) -> str:
    return json.dumps(dict(values), default=_json_default, separators=(",", ":"))


def _from_json(value: object) -> Mapping[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(str(value))


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize metadata value of type {type(value).__name__}")
