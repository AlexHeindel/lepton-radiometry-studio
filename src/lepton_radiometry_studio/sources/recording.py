from __future__ import annotations

from pathlib import Path

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.base import FrameSource
from lepton_radiometry_studio.storage import Hdf5RecordingReader


class Hdf5PlaybackSource(FrameSource):
    """Seekable radiometric playback source backed by an HDF5 recording."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.reader = Hdf5RecordingReader(self.path)
        if len(self.reader) == 0:
            self.reader.close()
            raise ValueError("The recording contains no frames")
        self._next_index = 0
        self._displayed_index = -1
        self._playing = False

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def nominal_fps(self) -> float:
        return self.reader.nominal_fps

    @property
    def frame_count(self) -> int:
        return len(self.reader)

    @property
    def current_index(self) -> int:
        return max(0, self._displayed_index)

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def duration_seconds(self) -> float:
        return self.reader.duration_seconds

    @property
    def elapsed_seconds(self) -> float:
        return self.reader.elapsed_seconds(self.current_index)

    def next_frame(self) -> ThermalFrame:
        index = self._next_index
        frame = self.reader.frame(index)
        self._displayed_index = index
        if self._playing and index < self.frame_count - 1:
            self._next_index = index + 1
        elif index >= self.frame_count - 1:
            self._playing = False
            self._next_index = index
        return frame

    def play(self) -> None:
        if self._displayed_index >= self.frame_count - 1:
            self._next_index = 0
        elif self._displayed_index >= 0:
            self._next_index = self._displayed_index + 1
        self._playing = True

    def pause(self) -> None:
        self._playing = False
        if self._displayed_index >= 0:
            self._next_index = self._displayed_index

    def seek(self, index: int) -> None:
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        self._playing = False
        self._next_index = index
        self._displayed_index = index

    def stop(self) -> None:
        self.reader.close()
