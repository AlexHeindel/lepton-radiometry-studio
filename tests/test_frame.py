import numpy as np
import pytest

from lepton_radiometry_studio.domain import ThermalFrame


def test_tlinear_temperature_conversion_and_coordinates() -> None:
    raw = np.array([[27315, 29315], [30315, 31315]], dtype=np.uint16)
    frame = ThermalFrame(raw=raw, timestamp_ns=123)

    assert frame.temperature_at_celsius(0, 0) == pytest.approx(0.0)
    assert frame.temperature_at_celsius(1, 0) == pytest.approx(20.0)
    assert frame.raw_at(1, 1) == 31315


def test_statistics_report_values_and_locations() -> None:
    raw = np.array([[30000, 29000], [31000, 30500]], dtype=np.uint16)
    stats = ThermalFrame(raw=raw, timestamp_ns=1).statistics()

    assert stats.minimum_xy == (1, 0)
    assert stats.maximum_xy == (0, 1)
    assert stats.minimum_c == pytest.approx(16.85, abs=1e-3)
    assert stats.maximum_c == pytest.approx(36.85, abs=1e-3)
    assert stats.mean_c == pytest.approx(28.10, abs=1e-3)


def test_frame_owns_read_only_copy() -> None:
    raw = np.full((2, 3), 30000, dtype=np.uint16)
    frame = ThermalFrame(raw=raw, timestamp_ns=1)
    raw[0, 0] = 1

    assert frame.raw_at(0, 0) == 30000
    with pytest.raises(ValueError):
        frame.raw[0, 0] = 2


@pytest.mark.parametrize(
    "raw,error",
    [
        (np.zeros((2, 2), dtype=np.float32), TypeError),
        (np.zeros((2, 2, 1), dtype=np.uint16), ValueError),
        (np.zeros((0, 0), dtype=np.uint16), ValueError),
    ],
)
def test_invalid_frame_data_is_rejected(raw, error) -> None:
    with pytest.raises(error):
        ThermalFrame(raw=raw, timestamp_ns=1)


def test_out_of_bounds_pixel_is_rejected() -> None:
    frame = ThermalFrame(raw=np.zeros((2, 2), dtype=np.uint16), timestamp_ns=1)
    with pytest.raises(IndexError):
        frame.temperature_at_celsius(2, 0)
