from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


SERIAL_PORT = "COM3"


@dataclass(frozen=True, slots=True)
class IndoorClimateReading:
    temperature: float
    humidity: float


class Thermometer(ABC):
    """Abstract indoor climate sensor interface."""

    @abstractmethod
    def connect(self) -> None:
        """Open the underlying device connection."""

    @abstractmethod
    def get_climate(self) -> IndoorClimateReading:
        """Read one temperature and humidity sample."""

    @abstractmethod
    def get_device_info(self) -> dict:
        """Return transport and sensor metadata."""

    def get_temperature(self) -> float:
        return self.get_climate().temperature

    def get_humidity(self) -> float:
        return self.get_climate().humidity


_thermometer: Optional[Thermometer] = None


def get_thermometer() -> Thermometer:
    """Return the process-wide thermometer implementation."""
    global _thermometer
    if _thermometer is None:
        from powers.io.sht4x_serial_sensor import SHT4xSerialThermometer

        _thermometer = SHT4xSerialThermometer(port=SERIAL_PORT)
    return _thermometer


def get_temperature() -> float:
    return get_thermometer().get_temperature()


def get_humidity() -> float:
    return get_thermometer().get_humidity()


def get_climate() -> IndoorClimateReading:
    return get_thermometer().get_climate()


if __name__ == "__main__":
    thermometer = get_thermometer()
    print("Device info:")
    for key, value in thermometer.get_device_info().items():
        print(f"  {key}: {value}")
    reading = thermometer.get_climate()
    print(f"Current temperature: {reading.temperature:.2f} C")
    print(f"Current humidity: {reading.humidity:.2f} %")
