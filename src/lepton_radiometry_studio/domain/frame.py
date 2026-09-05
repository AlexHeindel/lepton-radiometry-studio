from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class FrameStatistics:
    minimum_c: float
    maximum_c: float
    mean_c: float
    minimum_xy: Tuple[int, int]
    maximum_xy: Tuple[int, int]


@dataclass(frozen=True)
class ThermalFrame:
    """One immutable radiometric frame.

    `temperature_c = raw * temperature_scale + temperature_offset`
    """

    raw: NDArray[np.uint16]
    timestamp_ns: int
    temperature_scale: float = 0.01
    temperature_offset: float = -273.15
    telemetry: Mapping[str, Any] = field(default_factory=dict)
    camera_settings: Mapping[str, Any] = field(default_factory=dict)
    _statistics_cache: Optional[FrameStatistics] = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        raw = np.asarray(self.raw)
        if raw.ndim != 2:
            raise ValueError("Thermal frame must be a two-dimensional array")
        if raw.size == 0:
            raise ValueError("Thermal frame cannot be empty")
        if raw.dtype != np.uint16:
            raise TypeError("Thermal frame data must use uint16 values")
        if not np.isfinite(self.temperature_scale) or self.temperature_scale <= 0:
            raise ValueError("Temperature scale must be finite and positive")
        if not np.isfinite(self.temperature_offset):
            raise ValueError("Temperature offset must be finite")
        if self.timestamp_ns < 0:
            raise ValueError("Timestamp cannot be negative")

        owned = np.ascontiguousarray(raw.copy())
        owned.flags.writeable = False
        object.__setattr__(self, "raw", owned)
        object.__setattr__(self, "telemetry", MappingProxyType(dict(self.telemetry)))
        object.__setattr__(
            self, "camera_settings", MappingProxyType(dict(self.camera_settings))
        )

    @property
    def shape(self) -> Tuple[int, int]:
        return self.raw.shape

    @property
    def height(self) -> int:
        return self.raw.shape[0]

    @property
    def width(self) -> int:
        return self.raw.shape[1]

    def temperatures_celsius(self) -> NDArray[np.float32]:
        return self.raw.astype(np.float32) * self.temperature_scale + self.temperature_offset

    def raw_at(self, x: int, y: int) -> int:
        self._validate_coordinates(x, y)
        return int(self.raw[y, x])

    def temperature_at_celsius(self, x: int, y: int) -> float:
        return self.raw_at(x, y) * self.temperature_scale + self.temperature_offset

    def statistics(self) -> FrameStatistics:
        cached = self._statistics_cache
        if cached is not None:
            return cached
        min_y, min_x = np.unravel_index(int(np.argmin(self.raw)), self.raw.shape)
        max_y, max_x = np.unravel_index(int(np.argmax(self.raw)), self.raw.shape)
        statistics = FrameStatistics(
            minimum_c=(
                float(self.raw[min_y, min_x]) * self.temperature_scale
                + self.temperature_offset
            ),
            maximum_c=(
                float(self.raw[max_y, max_x]) * self.temperature_scale
                + self.temperature_offset
            ),
            mean_c=(
                float(np.mean(self.raw, dtype=np.float64)) * self.temperature_scale
                + self.temperature_offset
            ),
            minimum_xy=(int(min_x), int(min_y)),
            maximum_xy=(int(max_x), int(max_y)),
        )
        object.__setattr__(self, "_statistics_cache", statistics)
        return statistics

    def _validate_coordinates(self, x: int, y: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(
                f"Pixel ({x}, {y}) is outside frame bounds "
                f"0..{self.width - 1}, 0..{self.height - 1}"
            )
