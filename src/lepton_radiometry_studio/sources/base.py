from __future__ import annotations

from abc import ABC, abstractmethod

from lepton_radiometry_studio.domain import ThermalFrame


class FrameSource(ABC):
    """Hardware-independent source of complete radiometric frames."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    def nominal_fps(self) -> float:
        return 8.7

    def start(self) -> None:
        pass

    @abstractmethod
    def next_frame(self) -> ThermalFrame:
        raise NotImplementedError

    def stop(self) -> None:
        pass

    def run_ffc(self) -> None:
        raise NotImplementedError(f"{self.name} does not support FFC")

