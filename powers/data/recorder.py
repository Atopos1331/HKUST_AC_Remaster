import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

import requests

from powers.auth.ac_api import get_ac_api
from powers.data.global_state import (
    read_ac_is_on,
    read_indoor_climate,
)
from powers.utils.config import Recorder
from powers.utils.logger import log
from powers.utils.thermal import calculate_heat_index_c

DB_PATH = Recorder.DB_PATH
LATITUDE = Recorder.LATITUDE
LONGITUDE = Recorder.LONGITUDE

# Register datetime adapters so SQLite stores ISO-8601 strings transparently.
sqlite3.register_adapter(datetime, lambda v: v.replace(tzinfo=None).isoformat())
sqlite3.register_converter("DATETIME", lambda v: datetime.fromisoformat(v.decode()))
sqlite3.register_converter("TIMESTAMP", lambda v: datetime.fromisoformat(v.decode()))


class ACDataRecorder:
    """Write time-series measurements to the SQLite ``measurements`` table."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    ts      DATETIME NOT NULL,
                    metric  TEXT     NOT NULL,
                    value   TEXT,
                    tags    TEXT,
                    PRIMARY KEY (ts, metric)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measure_ts ON measurements(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measure_metric ON measurements(metric)")
            conn.commit()

    def _insert(self, rows: List[tuple]) -> None:
        """Bulk-insert measurement rows, replacing duplicates on (ts, metric)."""
        with self._lock:
            with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO measurements (ts, metric, value, tags) VALUES (?, ?, ?, ?)",
                    rows,
                )
                conn.commit()
        metric_names = ", ".join(row[1] for row in rows)
        log.info(f"[recorder] Persisted {len(rows)} measurement rows at {rows[0][0]} metrics=[{metric_names}]")

    def record(self) -> None:
        """Collect and persist one snapshot of indoor sensor and electrical data."""
        ts = datetime.now()
        rows: List[tuple] = []
        climate = read_indoor_climate()

        try:
            temperature = climate.temperature
            if temperature is not None:
                rows.append((ts, "temperature", str(temperature), None))
                log.detail(f"[recorder] Indoor temperature: {temperature} C")
        except Exception as e:
            log.warning(f"[recorder] Failed to read indoor temperature: {e}")

        try:
            humidity = climate.humidity
            if humidity is not None:
                rows.append((ts, "humidity", str(humidity), None))
                log.detail(f"[recorder] Indoor humidity: {humidity} %")
        except Exception as e:
            log.warning(f"[recorder] Failed to read indoor humidity: {e}")

        try:
            heat_index = climate.heat_index
            if heat_index is not None:
                rows.append((ts, "heat_index_c", str(heat_index), None))
                log.detail(f"[recorder] Indoor heat index: {heat_index:.2f} C")
        except Exception as e:
            log.warning(f"[recorder] Failed to read indoor heat index: {e}")

        try:
            ac_on = 1 if read_ac_is_on() else 0
            rows.append((ts, "ac_on", str(ac_on), None))
            log.detail(f"[recorder] AC state: {'on' if ac_on else 'off'}")
        except Exception as e:
            log.warning(f"[recorder] Failed to read AC state: {e}")

        api = get_ac_api()
        try:
            voltage, current, power_w, energy_wh = api.get_status()
            rows.extend(
                [
                    (ts, "ac_voltage", str(voltage), None),
                    (ts, "ac_current", str(current), None),
                    (ts, "ac_power_w", str(power_w), None),
                    (ts, "ac_energy_wh", str(energy_wh), None),
                ]
            )
            log.detail(
                f"[recorder] Electrical: V={voltage} V I={current} A P={power_w} W E={energy_wh} Wh"
            )
        except Exception as e:
            log.warning(f"[recorder] Failed to read electrical parameters: {e}")

        try:
            balance, total_paid = api.get_balance()
            rows.extend(
                [
                    (ts, "balance_min", str(balance), None),
                    (ts, "total_paid_min", str(total_paid), None),
                ]
            )
            log.detail(f"[recorder] Balance: {balance} min | Total paid: {total_paid} min")
        except Exception as e:
            log.warning(f"[recorder] Failed to read balance: {e}")

        if rows:
            self._insert(rows)
        else:
            log.warning("[recorder] No indoor or electrical data collected in this cycle.")

    def record_outdoor(self) -> None:
        """Fetch outdoor weather from Open-Meteo and persist it."""
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={LATITUDE}&longitude={LONGITUDE}"
                f"&current=temperature_2m,relative_humidity_2m"
            )
            data = requests.get(url, timeout=10).json()

            try:
                temperature = data["current"]["temperature_2m"]
                humidity = data["current"]["relative_humidity_2m"]
            except KeyError:
                weather = data.get("current_weather", {})
                temperature = weather.get("temperature")
                humidity = weather.get("relative_humidity")

            ts = datetime.now()
            rows: List[tuple] = []

            if temperature is not None:
                rows.append((ts, "outdoor_temp", str(temperature), json.dumps({"src": "open-meteo"})))
                log.detail(f"[recorder] Outdoor temp: {temperature} C")

            if humidity is not None:
                rows.append((ts, "outdoor_humidity", str(humidity), json.dumps({"src": "open-meteo"})))
                log.detail(f"[recorder] Outdoor humidity: {humidity} %")

            if temperature is not None and humidity is not None:
                heat_index = calculate_heat_index_c(float(temperature), float(humidity))
                rows.append(
                    (
                        ts,
                        "outdoor_heat_index_c",
                        f"{heat_index:.2f}",
                        json.dumps({"src": "open-meteo+noaa"}),
                    )
                )
                log.detail(f"[recorder] Outdoor heat index: {heat_index:.2f} C")

            if rows:
                self._insert(rows)
            else:
                log.warning("[recorder] Outdoor weather request succeeded but returned no usable values.")
        except Exception as e:
            log.warning(f"[recorder] Failed to fetch outdoor weather: {e}")


_recorder: Optional[ACDataRecorder] = None


def get_recorder() -> ACDataRecorder:
    """Return the process-wide ``ACDataRecorder`` singleton."""
    global _recorder
    if _recorder is None:
        _recorder = ACDataRecorder()
    return _recorder


if __name__ == "__main__":
    recorder = get_recorder()
    recorder.record()
    recorder.record_outdoor()
