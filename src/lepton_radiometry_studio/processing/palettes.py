from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from lepton_radiometry_studio.domain import PointMarker, RegionOfInterest, ThermalFrame

Color = Tuple[int, int, int]
ColorStop = Tuple[float, Color]

PALETTES: Dict[str, Sequence[ColorStop]] = {
    "Iron": (
        (0.00, (0, 0, 0)),
        (0.25, (55, 0, 80)),
        (0.50, (180, 35, 45)),
        (0.75, (255, 170, 25)),
        (1.00, (255, 255, 235)),
    ),
    "Inferno": (
        (0.00, (0, 0, 4)),
        (0.25, (87, 16, 110)),
        (0.50, (188, 55, 84)),
        (0.75, (249, 142, 9)),
        (1.00, (252, 255, 164)),
    ),
    "Grayscale": ((0.00, (0, 0, 0)), (1.00, (255, 255, 255))),
    "Rainbow": (
        (0.00, (0, 0, 120)),
        (0.20, (0, 120, 255)),
        (0.40, (0, 220, 150)),
        (0.60, (230, 230, 0)),
        (0.80, (255, 100, 0)),
        (1.00, (150, 0, 0)),
    ),
    "Cool/Warm": (
        (0.00, (45, 55, 180)),
        (0.50, (235, 235, 235)),
        (1.00, (180, 30, 45)),
    ),
}


def render_frame(
    frame: ThermalFrame,
    palette: str = "Iron",
    minimum_c: Optional[float] = None,
    maximum_c: Optional[float] = None,
) -> NDArray[np.uint8]:
    """Render a frame to RGB without changing its measurement data."""
    temperatures = frame.temperatures_celsius()
    low = float(np.min(temperatures)) if minimum_c is None else float(minimum_c)
    high = float(np.max(temperatures)) if maximum_c is None else float(maximum_c)
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError("Display range must be finite")
    if high <= low:
        high = low + 1e-6

    normalized = np.clip((temperatures - low) / (high - low), 0.0, 1.0)
    try:
        stops = PALETTES[palette]
    except KeyError as exc:
        raise ValueError(f"Unknown palette: {palette}") from exc

    positions = np.asarray([stop[0] for stop in stops], dtype=np.float32)
    colors = np.asarray([stop[1] for stop in stops], dtype=np.float32)
    flattened = normalized.ravel()
    rgb = np.empty((flattened.size, 3), dtype=np.float32)
    for channel in range(3):
        rgb[:, channel] = np.interp(flattened, positions, colors[:, channel])
    return np.rint(rgb).clip(0, 255).astype(np.uint8).reshape((*frame.shape, 3))


def render_visual_export(
    frame: ThermalFrame,
    palette: str = "Iron",
    show_extrema: bool = True,
    scale: int = 4,
    minimum_c: Optional[float] = None,
    maximum_c: Optional[float] = None,
    point_markers: Sequence[PointMarker] = (),
    regions: Sequence[RegionOfInterest] = (),
) -> NDArray[np.uint8]:
    """Render display settings and overlays without altering radiometric data."""
    if scale < 1:
        raise ValueError("Visual export scale must be at least 1")
    rgb = render_frame(
        frame, palette=palette, minimum_c=minimum_c, maximum_c=maximum_c
    )
    image = Image.fromarray(rgb)
    if scale != 1:
        image = image.resize(
            (frame.width * scale, frame.height * scale),
            Image.Resampling.LANCZOS,
        )
    draw = ImageDraw.Draw(image)
    if show_extrema:
        stats = frame.statistics()
        _draw_extrema_marker(draw, stats.minimum_xy, scale, "MIN", (77, 195, 255))
        _draw_extrema_marker(draw, stats.maximum_xy, scale, "MAX", (255, 219, 77))
    _draw_measurements(draw, point_markers, regions, scale)
    return np.asarray(image, dtype=np.uint8)


def _draw_extrema_marker(
    draw: ImageDraw.ImageDraw,
    point: Tuple[int, int],
    scale: int,
    label: str,
    color: Color,
) -> None:
    x = round((point[0] + 0.5) * scale)
    y = round((point[1] + 0.5) * scale)
    radius = max(4, 2 * scale)
    line_width = max(1, scale // 2)
    draw.line((x - radius, y, x + radius, y), fill=color, width=line_width)
    draw.line((x, y - radius, x, y + radius), fill=color, width=line_width)
    draw.text((x + radius + 2, max(0, y - radius - 4)), label, fill=color)


def _draw_measurements(
    draw: ImageDraw.ImageDraw,
    point_markers: Sequence[PointMarker],
    regions: Sequence[RegionOfInterest],
    scale: int,
) -> None:
    color = (105, 255, 145)
    line_width = max(1, scale // 2)
    radius = max(4, 2 * scale)
    for marker in point_markers:
        x = round((marker.x + 0.5) * scale)
        y = round((marker.y + 0.5) * scale)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            outline=color,
            width=line_width,
        )
        draw.line((x - radius, y, x + radius, y), fill=color, width=line_width)
        draw.line((x, y - radius, x, y + radius), fill=color, width=line_width)
        draw.text(
            (x + radius + 2, max(0, y - radius - 4)),
            f"P{marker.identifier}",
            fill=color,
        )
    for region in regions:
        left, top, right, bottom = region.bounds
        box = (
            left * scale,
            top * scale,
            (right + 1) * scale,
            (bottom + 1) * scale,
        )
        if region.kind == "circle":
            draw.ellipse(box, outline=color, width=line_width)
            prefix = "C"
        else:
            draw.rectangle(box, outline=color, width=line_width)
            prefix = "R"
        draw.text((box[0] + 3, box[1] + 3), f"{prefix}{region.identifier}", fill=color)
