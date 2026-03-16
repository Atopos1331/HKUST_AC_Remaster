from __future__ import annotations

import time

try:
    import serial
except ImportError:  # pragma: no cover - depends on local environment
    serial = None

from powers.io.thermometer import IndoorClimateReading, Thermometer
from powers.utils.logger import log


RETRY_TIMES = 5
TIMEOUT_MS = 2000
BAUD_RATE = 115200
SHT4X_ADDRESS = 0x44
SHT4X_MEASURE_COMMAND = 0xFD
SHT4X_MEASURE_DELAY_SEC = 0.01


class SHT4xSerialThermometer(Thermometer):
    """Read an SHT4x via a serial-to-I2C bridge."""

    def __init__(self, port: str) -> None:
        self.port = port
        self.device = None
        self.is_connected = False

    def connect(self) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed. Install it with `pip install pyserial`.")
        if self.is_connected and self.device:
            return
        try:
            self.device = serial.Serial(self.port, BAUD_RATE, timeout=TIMEOUT_MS / 1000)
            self.is_connected = True
            log.info(f"Climate sensor connected on {self.port} @ {BAUD_RATE} baud")
        except Exception as e:
            self.device = None
            self.is_connected = False
            log.error(f"Failed to connect to climate sensor: {e}")
            raise RuntimeError(f"Failed to connect to climate sensor: {e}") from e

    def _ensure_connected(self) -> None:
        if not self.is_connected or self.device is None:
            self.connect()

    def _i2c_write(self, addr: int, data: int | list[int]) -> None:
        self._ensure_connected()
        payload = data if isinstance(data, list) else [data]
        command = b"W" + bytes([addr, len(payload)]) + bytes(payload)
        self.device.write(command)
        response = self.device.read(1)
        if response != b"O":
            raise RuntimeError(f"I2C write error: {response!r}")

    def _i2c_read(self, addr: int, length: int) -> bytes:
        self._ensure_connected()
        command = b"R" + bytes([addr, length])
        self.device.write(command)
        response = self.device.read(1)
        if response != b"O":
            raise RuntimeError(f"I2C read error: {response!r}")
        data = self.device.read(length)
        if len(data) != length:
            raise RuntimeError(f"Incomplete I2C read: expected {length} bytes, got {len(data)}")
        return data

    @staticmethod
    def _crc8(data_bytes: bytes) -> int:
        crc = 0xFF
        for byte in data_bytes:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc <<= 1
                crc &= 0xFF
        return crc

    def get_climate(self) -> IndoorClimateReading:
        last_error: Exception | None = None
        for attempt in range(RETRY_TIMES):
            try:
                self._i2c_write(SHT4X_ADDRESS, [SHT4X_MEASURE_COMMAND])
                time.sleep(SHT4X_MEASURE_DELAY_SEC)
                raw = self._i2c_read(SHT4X_ADDRESS, 6)

                temp_bytes = raw[0:2]
                humidity_bytes = raw[3:5]
                if self._crc8(temp_bytes) != raw[2]:
                    raise RuntimeError("Temperature CRC error")
                if self._crc8(humidity_bytes) != raw[5]:
                    raise RuntimeError("Humidity CRC error")

                temp_ticks = raw[0] * 256 + raw[1]
                humidity_ticks = raw[3] * 256 + raw[4]

                temperature = -45 + 175 * temp_ticks / 65535
                humidity = -6 + 125 * humidity_ticks / 65535
                humidity = max(0.0, min(100.0, humidity))

                return IndoorClimateReading(temperature=temperature, humidity=humidity)
            except Exception as e:
                last_error = e
                log.warning(f"Climate read failed (attempt {attempt + 1}/{RETRY_TIMES}): {e}")
                self.is_connected = False
                self.device = None
                if attempt < RETRY_TIMES - 1:
                    time.sleep(0.5)

        raise RuntimeError(f"Climate read failed after all retries: {last_error}")

    def get_device_info(self) -> dict:
        return {
            "port": self.port,
            "baud_rate": BAUD_RATE,
            "sensor": "SHT4x",
            "i2c_address": hex(SHT4X_ADDRESS),
            "connected": self.is_connected,
        }
