from __future__ import annotations

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.base import FrameSource


class CameraUnavailableSource(FrameSource):
    """Idle source used while no live camera or saved capture is selected."""

    @property
    def name(self) -> str:
        return "Camera not found"

    def next_frame(self) -> ThermalFrame:
        raise RuntimeError("Camera not found")
