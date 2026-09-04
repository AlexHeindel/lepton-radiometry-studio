import pytest

from lepton_radiometry_studio.processing.units import (
    TemperatureUnit,
    convert_celsius,
    format_temperature,
)


@pytest.mark.parametrize(
    "unit,expected",
    [
        (TemperatureUnit.CELSIUS, 100.0),
        (TemperatureUnit.FAHRENHEIT, 212.0),
        (TemperatureUnit.KELVIN, 373.15),
    ],
)
def test_temperature_unit_conversion(unit: TemperatureUnit, expected: float) -> None:
    assert convert_celsius(100.0, unit) == pytest.approx(expected)


def test_temperature_format_includes_unit() -> None:
    assert format_temperature(20.0, TemperatureUnit.CELSIUS) == "20.00 °C"

