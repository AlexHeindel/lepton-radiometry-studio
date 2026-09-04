from __future__ import annotations

from pathlib import Path

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.base import FrameSource
from lepton_radiometry_studio.storage.stills import load_still


class StillFileSource(FrameSource):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._frame = load_still(self.path)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def nominal_fps(self) -> float:
        return 1.0

    def next_frame(self) -> ThermalFrame:
        return self._frame

