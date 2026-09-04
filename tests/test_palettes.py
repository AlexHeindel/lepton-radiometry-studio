import numpy as np
import pytest

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing.palettes import PALETTES, render_frame


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

