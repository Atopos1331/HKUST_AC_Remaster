from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
import threading
from typing import Any, Mapping, Optional

from powers.utils.config import Config
from powers.utils.logger import log


EPOCH_ISO = "1970-01-01T00:00:00"


@dataclass(frozen=True, slots=True)
class ACSettings:
    switch: int = 1
    control_mode: str = "temperature"
    target_temp: float = 29.5
    temperature_control_basis: str = "temperature"
    temp_threshold_high: float = Config.TEMP_THRESHOLD_HIGH
    temp_threshold_low: float = Config.TEMP_THRESHOLD_LOW
    cooldown_time: int = Config.COOLDOWN_TIME
    ontime: int = Config.DEFAULT_ONTIME
    offtime: int = Config.DEFAULT_OFFTIME
    lock_status: bool = False
    lock_end_time: str = EPOCH_ISO

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_updates(self, **updates: Any) -> "ACSettings":
        valid_fields = {field.name for field in fields(type(self))}
        valid_updates = {key: value for key, value in updates.items() if key in valid_fields}
        for key in updates.keys() - valid_fields:
            log.warning(f"Unknown setting key: {key!r}")
        if not valid_updates:
            return self
        return replace(self, **valid_updates)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ACSettings":
        valid_fields = {field.name for field in fields(cls)}
        filtered = {key: value for key, value in data.items() if key in valid_fields}
        return cls(**filtered)


class JSONSettingsRepository:
    def __init__(self, file_path: str | Path = Config.SETTINGS_JSON_PATH) -> None:
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._cache: dict[str, Any] | None = None
        self._cache_mtime_ns: int | None = None
        self._ensure_store()

    def _ensure_store(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write_raw(ACSettings().to_dict())

    def _write_raw(self, data: Mapping[str, Any]) -> None:
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, ensure_ascii=True, indent=2, sort_keys=True)

    def _load_raw(self) -> dict[str, Any]:
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return ACSettings().to_dict()
        except Exception as exc:
            log.warning(f"Failed to load settings JSON from {self.file_path}: {exc}")
            return ACSettings().to_dict()

        if not isinstance(data, dict):
            log.warning(f"Settings JSON in {self.file_path} is not an object; falling back to defaults")
            return ACSettings().to_dict()
        return data

    def _get_mtime_ns(self) -> int | None:
        try:
            return self.file_path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def load_all(self) -> dict[str, Any]:
        with self._lock:
            current_mtime_ns = self._get_mtime_ns()
            if self._cache is None or self._cache_mtime_ns != current_mtime_ns:
                self._cache = self._load_raw()
                self._cache_mtime_ns = current_mtime_ns
            return dict(self._cache)

    def save_all(self, data: Mapping[str, Any]) -> None:
        normalized = dict(data)
        with self._lock:
            current_mtime_ns = self._get_mtime_ns()
            if self._cache is None or self._cache_mtime_ns != current_mtime_ns:
                self._cache = self._load_raw()
                self._cache_mtime_ns = current_mtime_ns
            if self._cache == normalized:
                return
            self._write_raw(normalized)
            self._cache = dict(normalized)
            self._cache_mtime_ns = self._get_mtime_ns()
            log.detail("Settings JSON saved.")


class ACSettingsManager:
    def __init__(self, repo: Optional[JSONSettingsRepository] = None) -> None:
        self.repo = repo or JSONSettingsRepository()
        self._lock = threading.RLock()

    def load(self) -> ACSettings:
        return ACSettings.from_dict(self.repo.load_all())

    def load_settings(self) -> dict[str, Any]:
        return self.load().to_dict()

    def save(self, settings: ACSettings) -> ACSettings:
        self.repo.save_all(settings.to_dict())
        return settings

    def save_settings(self, settings_dict: Mapping[str, Any]) -> ACSettings:
        return self.save(ACSettings.from_dict(settings_dict))

    def get_setting(self, key: str, default: Any = None) -> Any:
        return getattr(self.load(), key, default)

    def set_setting(self, key: str, value: Any) -> ACSettings:
        return self.update(**{key: value})

    def update(self, **updates: Any) -> ACSettings:
        with self._lock:
            settings = self.load()
            updated = settings.with_updates(**updates)
            return self.save(updated)

    def update_multiple_settings(self, updates: Mapping[str, Any]) -> ACSettings:
        return self.update(**dict(updates))


_settings_manager: ACSettingsManager | None = None
_settings_manager_lock = threading.Lock()


def get_settings_manager() -> ACSettingsManager:
    global _settings_manager
    if _settings_manager is None:
        with _settings_manager_lock:
            if _settings_manager is None:
                _settings_manager = ACSettingsManager()
    return _settings_manager


if __name__ == "__main__":
    manager = get_settings_manager()
    manager.update(target_temp=30.2)
    for key, value in manager.load().to_dict().items():
        print(f"  {key}: {value}")
