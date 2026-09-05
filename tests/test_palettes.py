import numpy as np
import pytest

from lepton_radiometry_studio.domain import PointMarker, RegionOfInterest, ThermalFrame
from lepton_radiometry_studio.processing.palettes import (
    PALETTES,
    render_frame,
    render_visual_export,
)


@pytest.fixture
def frame() -> ThermalFrame:
    return ThermalFrame(
        raw=np.array([[28000, 29000], [30000, 31000]], dtype=np.uint16),
        timestamp_ns=1,
    )


@pytest.mark.parametrize("palette", PALETTES.keys())
def test_each_palette_renders_rgb_uint8(frame: ThermalFrame, palette: str) -> None:
    image = render_frame(frame, palette)
    assert image.shape == (2, 2, 3)
    assert image.dtype == np.uint8


def test_manual_range_clips_values(frame: ThermalFrame) -> None:
    image = render_frame(frame, "Grayscale", minimum_c=16.85, maximum_c=26.85)
    assert tuple(image[0, 0]) == (0, 0, 0)
    assert tuple(image[1, 1]) == (255, 255, 255)


def test_unknown_palette_is_rejected(frame: ThermalFrame) -> None:
    with pytest.raises(ValueError):
        render_frame(frame, "Not a palette")


def test_visual_export_applies_palette_scale_and_marker_setting(
    frame: ThermalFrame,
) -> None:
    plain = render_visual_export(frame, "Grayscale", show_extrema=False, scale=4)
    marked = render_visual_export(frame, "Grayscale", show_extrema=True, scale=4)

    assert plain.shape == (8, 8, 3)
    assert marked.shape == plain.shape
    assert not np.array_equal(marked, plain)


def test_visual_export_uses_manual_range_and_persistent_overlays(
    frame: ThermalFrame,
) -> None:
    plain = render_visual_export(
        frame,
        "Grayscale",
        show_extrema=False,
        minimum_c=16.85,
        maximum_c=26.85,
    )
    annotated = render_visual_export(
        frame,
        "Grayscale",
        show_extrema=False,
        minimum_c=16.85,
        maximum_c=26.85,
        point_markers=[PointMarker(1, 0, 0)],
        regions=[RegionOfInterest(1, "rectangle", 0, 0, 1, 1)],
    )

    assert tuple(plain[0, 0]) == (0, 0, 0)
    assert tuple(plain[-1, -1]) == (255, 255, 255)
    assert not np.array_equal(annotated, plain)
