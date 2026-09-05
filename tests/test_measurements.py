import numpy as np
import pytest

from lepton_radiometry_studio.domain import (
    RegionOfInterest,
    ThermalFrame,
    region_mask,
    region_statistics,
)


@pytest.fixture
def frame() -> ThermalFrame:
    return ThermalFrame(
        raw=np.arange(25, dtype=np.uint16).reshape(5, 5) + 27315,
        timestamp_ns=1,
    )


def test_rectangle_roi_statistics_use_original_radiometric_pixels(
    frame: ThermalFrame,
) -> None:
    region = RegionOfInterest(1, "rectangle", 1, 1, 3, 2)
    stats = region_statistics(frame, region)

    assert stats.pixel_count == 6
    assert stats.minimum_c == pytest.approx(0.06, abs=1e-4)
    assert stats.maximum_c == pytest.approx(0.13, abs=1e-4)
    assert stats.mean_c == pytest.approx(0.095, abs=1e-4)
    assert stats.minimum_xy == (1, 1)
    assert stats.maximum_xy == (3, 2)


def test_circle_roi_uses_an_elliptical_pixel_mask(frame: ThermalFrame) -> None:
    region = RegionOfInterest(1, "circle", 0, 0, 4, 4)
    mask = region_mask(frame.shape, region)

    assert mask[2, 2]
    assert not mask[0, 0]
    assert region_statistics(frame, region).pixel_count == 21


def test_invalid_roi_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="rectangle or circle"):
        RegionOfInterest(1, "triangle", 0, 0, 1, 1)
