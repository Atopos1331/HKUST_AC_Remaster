from __future__ import annotations

from powers.io.thermometer import IndoorClimateReading, Thermometer


DEFAULT_TEMPERATURE = 26.0
DEFAULT_HUMIDITY = 55.0


class DefaultThermometer(Thermometer):
    """Fallback thermometer that returns fixed indoor climate values."""

    def connect(self) -> None:
        return

    def get_climate(self) -> IndoorClimateReading:
        return IndoorClimateReading(
            temperature=DEFAULT_TEMPERATURE,
            humidity=DEFAULT_HUMIDITY,
        )

    def get_device_info(self) -> dict:
        return {
            "driver": "default",
            "sensor": "temperature_humidity_sensor",
            "temperature": DEFAULT_TEMPERATURE,
            "humidity": DEFAULT_HUMIDITY,
        }
