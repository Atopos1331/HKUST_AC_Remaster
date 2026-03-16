from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import threading
from typing import Any, Deque, Dict, List, Optional, TypedDict

from powers.utils.config import Config
from powers.utils.thermal import calculate_heat_index_c_optional


EPOCH = datetime(1970, 1, 1)


class HistoryRecord(TypedDict):
    time: datetime
    action: Optional[str]
    next_time: Optional[datetime]
    info: Dict[str, Any]


class HistoryBuffer:
    """Small thread-safe FIFO buffer for recent runtime history."""

    def __init__(self, max_size: int = Config.MAX_RECORDS) -> None:
        self._records: Deque[HistoryRecord] = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def append(self, record: HistoryRecord) -> None:
        with self._lock:
            self._records.append(record)

    def read_all(self) -> List[HistoryRecord]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


@dataclass(slots=True)
class IndoorClimateSnapshot:
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    heat_index: Optional[float] = None


@dataclass(slots=True)
class GlobalState:
    """Process-wide runtime state shared by control, bot, and recorder modules."""

    indoor_climate: IndoorClimateSnapshot = field(default_factory=IndoorClimateSnapshot)
    ac_is_on: Optional[bool] = None
    last_switch: datetime = EPOCH
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _decisions: HistoryBuffer = field(default_factory=HistoryBuffer, init=False, repr=False)
    _applied: HistoryBuffer = field(default_factory=HistoryBuffer, init=False, repr=False)

    def update_indoor_climate(self, temperature: float, humidity: float) -> None:
        with self._lock:
            self.indoor_climate = IndoorClimateSnapshot(
                temperature=temperature,
                humidity=humidity,
                heat_index=calculate_heat_index_c_optional(temperature, humidity),
            )

    def get_indoor_climate(self) -> IndoorClimateSnapshot:
        with self._lock:
            return IndoorClimateSnapshot(
                temperature=self.indoor_climate.temperature,
                humidity=self.indoor_climate.humidity,
                heat_index=self.indoor_climate.heat_index,
            )

    def get_temperature(self) -> Optional[float]:
        with self._lock:
            return self.indoor_climate.temperature

    def get_humidity(self) -> Optional[float]:
        with self._lock:
            return self.indoor_climate.humidity

    def get_heat_index(self) -> Optional[float]:
        with self._lock:
            return self.indoor_climate.heat_index

    def set_ac_is_on(self, value: Optional[bool]) -> None:
        with self._lock:
            self.ac_is_on = value

    def get_ac_is_on(self) -> Optional[bool]:
        with self._lock:
            return self.ac_is_on

    def set_last_switch(self, value: Optional[datetime]) -> None:
        with self._lock:
            self.last_switch = value or EPOCH

    def get_last_switch(self) -> datetime:
        with self._lock:
            return self.last_switch

    def add_decision(
        self,
        action: Optional[str],
        next_time: Optional[datetime],
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._decisions.append(self._build_record(action, next_time, info))

    def add_applied(
        self,
        action: Optional[str],
        next_time: Optional[datetime],
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._applied.append(self._build_record(action, next_time, info))

    def get_recent_decisions(self) -> List[HistoryRecord]:
        return self._decisions.read_all()

    def get_recent_applied(self) -> List[HistoryRecord]:
        return self._applied.read_all()

    def clear_history(self) -> None:
        self._decisions.clear()
        self._applied.clear()

    @staticmethod
    def _build_record(
        action: Optional[str],
        next_time: Optional[datetime],
        info: Optional[Dict[str, Any]],
    ) -> HistoryRecord:
        return {
            "time": datetime.now(),
            "action": action,
            "next_time": next_time,
            "info": dict(info or {}),
        }


_state: Optional[GlobalState] = None
_state_lock = threading.Lock()


def get_global_state() -> GlobalState:
    """Return the process-wide global state singleton."""
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = GlobalState()
    return _state


def reset_global_state() -> None:
    """Reset the global state singleton, mainly for tests."""
    global _state
    with _state_lock:
        _state = None


def read_temperature() -> Optional[float]:
    return get_global_state().get_temperature()


def read_indoor_climate() -> IndoorClimateSnapshot:
    return get_global_state().get_indoor_climate()


def read_humidity() -> Optional[float]:
    return get_global_state().get_humidity()


def read_heat_index() -> Optional[float]:
    return get_global_state().get_heat_index()


def write_indoor_climate(temperature: float, humidity: float) -> None:
    get_global_state().update_indoor_climate(temperature, humidity)


def read_ac_is_on() -> Optional[bool]:
    return get_global_state().get_ac_is_on()


def write_ac_is_on(value: Optional[bool]) -> None:
    get_global_state().set_ac_is_on(value)


def read_last_switch() -> datetime:
    return get_global_state().get_last_switch()


def write_last_switch(value: Optional[datetime]) -> None:
    get_global_state().set_last_switch(value)


def add_recent_decision(
    action: Optional[str],
    next_time: Optional[datetime],
    info: Optional[Dict[str, Any]] = None,
) -> None:
    get_global_state().add_decision(action, next_time, info)


def add_recent_applied(
    action: Optional[str],
    next_time: Optional[datetime],
    info: Optional[Dict[str, Any]] = None,
) -> None:
    get_global_state().add_applied(action, next_time, info)


def read_recent_decisions() -> List[HistoryRecord]:
    return get_global_state().get_recent_decisions()


def read_recent_applied() -> List[HistoryRecord]:
    return get_global_state().get_recent_applied()


def clear_global_history() -> None:
    get_global_state().clear_history()


__all__ = [
    "GlobalState",
    "HistoryBuffer",
    "HistoryRecord",
    "IndoorClimateSnapshot",
    "add_recent_applied",
    "add_recent_decision",
    "clear_global_history",
    "get_global_state",
    "read_ac_is_on",
    "read_heat_index",
    "read_humidity",
    "read_indoor_climate",
    "read_last_switch",
    "read_recent_applied",
    "read_recent_decisions",
    "read_temperature",
    "reset_global_state",
    "write_ac_is_on",
    "write_indoor_climate",
    "write_last_switch",
]
