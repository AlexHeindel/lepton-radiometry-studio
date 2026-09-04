from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import h5py
import numpy as np

from lepton_radiometry_studio.domain import ThermalFrame


class Hdf5RecordingWriter:
    """Append-only radiometric recording with explicit frame timestamps."""

    def __init__(self, path: Path, first_frame: ThermalFrame) -> None:
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
        self._file.attrs["format_version"] = 1
        self._file.attrs["temperature_scale"] = first_frame.temperature_scale
        self._file.attrs["temperature_offset"] = first_frame.temperature_offset
        self._file.attrs["telemetry"] = json.dumps(dict(first_frame.telemetry))
        self._file.attrs["camera_settings"] = json.dumps(dict(first_frame.camera_settings))
        self._closed = False

    @property
    def frame_count(self) -> int:
        return int(self._frames.shape[0])

    def append(self, frame: ThermalFrame) -> None:
        if self._closed:
            raise RuntimeError("Recording is closed")
        if frame.shape != self._frames.shape[1:]:
            raise ValueError("All recording frames must have the same dimensions")
        index = self.frame_count
        self._frames.resize(index + 1, axis=0)
        self._timestamps.resize(index + 1, axis=0)
        self._frames[index] = frame.raw
        self._timestamps[index] = frame.timestamp_ns
        if index % 16 == 0:
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
        self._frames = self._file["frames"]
        self._timestamps = self._file["timestamps_ns"]

    def __len__(self) -> int:
        return int(self._frames.shape[0])

    def frame(self, index: int) -> ThermalFrame:
        if not 0 <= index < len(self):
            raise IndexError(index)
        return ThermalFrame(
            raw=np.asarray(self._frames[index], dtype=np.uint16),
            timestamp_ns=int(self._timestamps[index]),
            temperature_scale=float(self._file.attrs["temperature_scale"]),
            temperature_offset=float(self._file.attrs["temperature_offset"]),
            telemetry=json.loads(self._file.attrs.get("telemetry", "{}")),
            camera_settings=json.loads(self._file.attrs.get("camera_settings", "{}")),
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
