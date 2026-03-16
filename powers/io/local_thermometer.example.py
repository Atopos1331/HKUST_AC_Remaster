from __future__ import annotations

from powers.io.thermometer import IndoorClimateReading, Thermometer


class LocalThermometer(Thermometer):
    """Example local-only thermometer implementation."""

    def connect(self) -> None:
        return

    def get_climate(self) -> IndoorClimateReading:
        return IndoorClimateReading(temperature=26.0, humidity=55.0)

    def get_device_info(self) -> dict:
        return {
            "driver": "local",
            "sensor": "temperature_humidity_sensor",
        }
