from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

import numpy as np

from .frame import ThermalFrame


@dataclass(frozen=True)
class PointMarker:
    identifier: int
    x: int
    y: int

    def to_dict(self) -> Mapping[str, Any]:
        return {"id": self.identifier, "x": self.x, "y": self.y}


@dataclass(frozen=True)
class RegionOfInterest:
    identifier: int
    kind: str
    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if self.kind not in {"rectangle", "circle"}:
            raise ValueError("ROI kind must be rectangle or circle")

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "id": self.identifier,
            "kind": self.kind,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }


@dataclass(frozen=True)
class RegionStatistics:
    minimum_c: float
    maximum_c: float
    mean_c: float
    pixel_count: int
    minimum_xy: Tuple[int, int]
    maximum_xy: Tuple[int, int]


def region_mask(shape: Tuple[int, int], region: RegionOfInterest) -> np.ndarray:
    """Return an ROI mask in source-pixel coordinates."""
    height, width = shape
    left, top, right, bottom = region.bounds
    left = min(width - 1, max(0, left))
    right = min(width - 1, max(0, right))
    top = min(height - 1, max(0, top))
    bottom = min(height - 1, max(0, bottom))
    yy, xx = np.ogrid[:height, :width]
    if region.kind == "rectangle":
        return (xx >= left) & (xx <= right) & (yy >= top) & (yy <= bottom)

    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    radius_x = max(0.5, (right - left + 1) / 2.0)
    radius_y = max(0.5, (bottom - top + 1) / 2.0)
    return (
        ((xx - center_x) / radius_x) ** 2
        + ((yy - center_y) / radius_y) ** 2
        <= 1.0
    )


def region_statistics(
    frame: ThermalFrame, region: RegionOfInterest
) -> RegionStatistics:
    mask = region_mask(frame.shape, region)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("Region does not contain a source pixel")
    values = frame.raw[mask]
    minimum_index = int(np.argmin(values))
    maximum_index = int(np.argmax(values))
    return RegionStatistics(
        minimum_c=(
            float(values[minimum_index]) * frame.temperature_scale
            + frame.temperature_offset
        ),
        maximum_c=(
            float(values[maximum_index]) * frame.temperature_scale
            + frame.temperature_offset
        ),
        mean_c=(
            float(np.mean(values, dtype=np.float64)) * frame.temperature_scale
            + frame.temperature_offset
        ),
        pixel_count=int(values.size),
        minimum_xy=(int(xs[minimum_index]), int(ys[minimum_index])),
        maximum_xy=(int(xs[maximum_index]), int(ys[maximum_index])),
    )


def point_marker_from_dict(value: Mapping[str, Any]) -> PointMarker:
    return PointMarker(int(value["id"]), int(value["x"]), int(value["y"]))


def region_from_dict(value: Mapping[str, Any]) -> RegionOfInterest:
    return RegionOfInterest(
        int(value["id"]),
        str(value["kind"]),
        int(value["x0"]),
        int(value["y0"]),
        int(value["x1"]),
        int(value["y1"]),
    )
