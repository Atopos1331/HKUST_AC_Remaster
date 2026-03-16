from typing import Optional


def calculate_heat_index_c(temperature_c: float, humidity: float) -> float:
    """Return the NOAA heat index in Celsius."""
    temperature_f = temperature_c * 9 / 5 + 32.0
    relative_humidity = max(0.0, min(100.0, float(humidity)))

    heat_index_f = (
        -42.379
        + 2.04901523 * temperature_f
        + 10.14333127 * relative_humidity
        - 0.22475541 * temperature_f * relative_humidity
        - 6.83783e-3 * temperature_f * temperature_f
        - 5.481717e-2 * relative_humidity * relative_humidity
        + 1.22874e-3 * temperature_f * temperature_f * relative_humidity
        + 8.5282e-4 * temperature_f * relative_humidity * relative_humidity
        - 1.99e-6 * temperature_f * temperature_f * relative_humidity * relative_humidity
    )

    if relative_humidity < 13 and 80 <= temperature_f <= 112:
        heat_index_f -= ((13 - relative_humidity) / 4) * ((17 - abs(temperature_f - 95)) / 17)
    elif relative_humidity > 85 and 80 <= temperature_f <= 87:
        heat_index_f += ((relative_humidity - 85) / 10) * ((87 - temperature_f) / 5)

    return (heat_index_f - 32.0) * 5 / 9


def calculate_heat_index_c_optional(
    temperature_c: Optional[float],
    humidity: Optional[float],
) -> Optional[float]:
    """Return heat index when both inputs are present, otherwise ``None``."""
    if temperature_c is None or humidity is None:
        return None
    return calculate_heat_index_c(float(temperature_c), float(humidity))
