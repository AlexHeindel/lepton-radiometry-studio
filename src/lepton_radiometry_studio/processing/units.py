from enum import Enum


class TemperatureUnit(str, Enum):
    CELSIUS = "°C"
    FAHRENHEIT = "°F"
    KELVIN = "K"


def convert_celsius(value_c: float, unit: TemperatureUnit) -> float:
    if unit is TemperatureUnit.CELSIUS:
        return value_c
    if unit is TemperatureUnit.FAHRENHEIT:
        return value_c * 9.0 / 5.0 + 32.0
    if unit is TemperatureUnit.KELVIN:
        return value_c + 273.15
    raise ValueError(f"Unknown temperature unit: {unit}")


def format_temperature(value_c: float, unit: TemperatureUnit) -> str:
    return f"{convert_celsius(value_c, unit):.2f} {unit.value}"

