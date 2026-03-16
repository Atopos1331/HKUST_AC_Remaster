from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib import import_module
from typing import Optional


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


def _build_default_thermometer() -> Thermometer:
    from powers.io.default_thermometer import DefaultThermometer

    return DefaultThermometer()


def _build_local_thermometer() -> Thermometer | None:
    try:
        module = import_module("powers.io.local_thermometer")
    except ModuleNotFoundError:
        return None

    factory = getattr(module, "get_thermometer", None)
    if callable(factory):
        thermometer = factory()
        if not isinstance(thermometer, Thermometer):
            raise TypeError("powers.io.local_thermometer.get_thermometer() must return a Thermometer")
        return thermometer

    local_class = getattr(module, "LocalThermometer", None)
    if local_class is None:
        raise AttributeError(
            "powers.io.local_thermometer must define LocalThermometer or get_thermometer()"
        )

    thermometer = local_class()
    if not isinstance(thermometer, Thermometer):
        raise TypeError("powers.io.local_thermometer.LocalThermometer must inherit from Thermometer")
    return thermometer


def get_thermometer() -> Thermometer:
    """Return the process-wide thermometer implementation."""
    global _thermometer
    if _thermometer is None:
        _thermometer = _build_local_thermometer() or _build_default_thermometer()
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
