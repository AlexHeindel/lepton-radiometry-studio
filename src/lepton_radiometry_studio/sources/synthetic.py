from __future__ import annotations

import time

import numpy as np

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.base import FrameSource


class SyntheticSource(FrameSource):
    """Deterministic moving thermal scene for desktop development."""

    def __init__(self, width: int = 160, height: int = 120) -> None:
        self.width = width
        self.height = height
        self._frame_index = 0
        y, x = np.mgrid[0:height, 0:width]
        self._x = x.astype(np.float32)
        self._y = y.astype(np.float32)

    @property
    def name(self) -> str:
        return "Synthetic Lepton 3.5"

    def next_frame(self) -> ThermalFrame:
        t = self._frame_index / self.nominal_fps
        background_c = 20.0 + 7.0 * self._x / max(1, self.width - 1)
        ripple_c = 0.8 * np.sin(self._y / 10.0 + t * 0.7)

        hot_x = self.width * (0.50 + 0.30 * np.sin(t * 0.45))
        hot_y = self.height * (0.50 + 0.25 * np.cos(t * 0.63))
        hot_spot_c = 18.0 * np.exp(
            -(
                ((self._x - hot_x) ** 2) / (2.0 * 12.0**2)
                + ((self._y - hot_y) ** 2) / (2.0 * 9.0**2)
            )
        )

        cold_x = self.width * (0.28 + 0.08 * np.cos(t * 0.31))
        cold_y = self.height * 0.28
        cold_spot_c = -5.0 * np.exp(
            -(
                ((self._x - cold_x) ** 2) / (2.0 * 9.0**2)
                + ((self._y - cold_y) ** 2) / (2.0 * 8.0**2)
            )
        )

        temperatures_c = background_c + ripple_c + hot_spot_c + cold_spot_c
        raw = np.rint((temperatures_c + 273.15) / 0.01).astype(np.uint16)
        frame = ThermalFrame(
            raw=raw,
            timestamp_ns=time.time_ns(),
            telemetry={"source": "synthetic", "frame_index": self._frame_index},
            camera_settings={"radiometric": True, "tlinear_resolution_k": 0.01},
        )
        self._frame_index += 1
        return frame

