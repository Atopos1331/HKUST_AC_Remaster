import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

from powers.utils.logger import log
from powers.utils.config import Config


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPOCH_ISO = '1970-01-01T00:00:00'


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


@dataclass
class ACSettings:
    """
    Persistent configuration for the AC controller.

    Stored in a JSON file. This dataclass is a typed view over the persisted
    JSON object.
    """

    # Master switch (1 = enabled, 0 = disabled)
    switch: int = 1

    # 'temperature' or 'scheduler'
    control_mode: str = "temperature"

    # Target indoor control metric (temperature or heat index, unit: °C)
    target_temp: float = 29.5

    # Metric used inside temperature control mode
    temperature_control_basis: str = "temperature" # "temperature" or "heat_index"

    # Temperature-mode hysteresis thresholds
    temp_threshold_high: float = Config.TEMP_THRESHOLD_HIGH
    temp_threshold_low: float = Config.TEMP_THRESHOLD_LOW

    # Minimum seconds between consecutive AC toggles
    cooldown_time: int = Config.COOLDOWN_TIME

    # Scheduler-mode on/off durations (seconds)
    ontime: int = Config.DEFAULT_ONTIME
    offtime: int = Config.DEFAULT_OFFTIME

    # Temporary lock that keeps the AC in a fixed state until lock_end_time
    lock_status: bool = False
    lock_end_time: str = EPOCH_ISO

    def to_dict(self) -> Dict[str, Any]:
        """Return the settings as a plain dict (datetime values preserved)."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ACSettings":
        """
        Construct an :class:`ACSettings` from a dict.

        All values are passed through as-is since json.load returns the
        correct Python types for our fields.
        """
        valid = {f.name for f in fields(ACSettings)}
        kwargs = {k: v for k, v in data.items() if k in valid}
        s = ACSettings(**kwargs)
        return s

# ---------------------------------------------------------------------------
# JSON repository with in-process cache
# ---------------------------------------------------------------------------


class JSONSettingsRepository:
    """
    Persist settings in a JSON file.

    The repository stores one JSON object:
    - _load_raw() reads the full document
    - save_all() rewrites the file only when content changed
    - _cache avoids repeated reads within the process
    """

    def __init__(self) -> None:
        self.file_path = Config.SETTINGS_JSON_PATH
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._cache_loaded: bool = False
        self._ensure_store()

    def _ensure_store(self) -> None:
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if os.path.exists(self.file_path):
            return
        self._write_raw(ACSettings().to_dict())

    def _write_raw(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, indent=2, sort_keys=True)

    def _load_raw(self) -> Dict[str, Any]:
        """
        Read the full JSON document from disk.

        This method does not acquire locks; callers handle synchronization.
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return ACSettings().to_dict()
        except Exception as e:
            log.warning(f"Failed to load settings JSON from {self.file_path}: {e}")
            return ACSettings().to_dict()

        if not isinstance(data, dict):
            log.warning(f"Settings JSON in {self.file_path} is not an object; falling back to defaults")
            return ACSettings().to_dict()
        return data

    def load_all(self) -> Dict[str, Any]:
        """
        Return the full JSON settings document.

        The repository loads from disk once and then serves copies of the
        in-process cache.
        """
        with self._lock:
            if not self._cache_loaded:
                try:
                    self._cache = self._load_raw()
                    self._cache_loaded = True
                except Exception as e:
                    log.warning(f"Failed to load settings JSON from {self.file_path}: {e}")
                    self._cache = ACSettings().to_dict()
                    self._cache_loaded = True
            # Return a copy so callers cannot mutate the cache directly.
            return dict(self._cache)

    def save_all(self, data: Dict[str, Any]) -> None:
        """
        Persist the full JSON settings document.

        The repository only rewrites the file when content actually changed.
        """
        with self._lock:
            try:
                if not self._cache_loaded:
                    self._cache = self._load_raw()
                    self._cache_loaded = True
                if self._cache == data:
                    return
                self._write_raw(data)
                self._cache = dict(data)
                log.detail("Settings JSON saved.")
            except Exception as e:
                log.error(f"Failed to save settings JSON to {self.file_path}: {e}")


# ---------------------------------------------------------------------------
# Settings manager (public API)
# ---------------------------------------------------------------------------


class ACSettingsManager:
    """
    High-level interface for reading and writing AC settings.

    Callers work with ACSettings or plain dict values, while the repository
    remains a simple JSON document store.
    """

    def __init__(self, repo: Optional[JSONSettingsRepository] = None) -> None:
        self.repo = repo or JSONSettingsRepository()
        self._lock = threading.Lock()

    # ---------- JSON <-> ACSettings mapping ----------

    def _data_to_settings(self, data: Dict[str, Any]) -> ACSettings:
        """
        Convert the stored JSON object into a typed ACSettings instance.
        """
        return ACSettings.from_dict(data)

    def _settings_to_data(self, settings: ACSettings) -> Dict[str, Any]:
        """
        Convert ACSettings into the persisted JSON representation.
        """
        return settings.to_dict()

    # ---------- Public API ----------

    def load_settings(self) -> Dict[str, Any]:
        """
        Return all settings as a plain dict (datetime preserved).
        """
        data = self.repo.load_all()
        settings = self._data_to_settings(data)
        return settings.to_dict()

    def save_settings(self, settings_dict: Dict[str, Any]) -> None:
        """
        Overwrite all settings from a plain dict.
        """
        settings = ACSettings.from_dict(settings_dict)
        data = self._settings_to_data(settings)
        self.repo.save_all(data)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Read a single setting by name.
        """
        settings_dict = self.load_settings()
        return settings_dict.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """
        Update a single setting by name.
        """
        with self._lock:
            data = self.repo.load_all()
            settings = self._data_to_settings(data)
            if hasattr(settings, key):
                setattr(settings, key, value)
                new_data = self._settings_to_data(settings)
                self.repo.save_all(new_data)
            else:
                log.warning(f"Unknown setting key: {key!r}")

    def update_multiple_settings(self, updates: Dict[str, Any]) -> None:
        """
        Atomically update multiple settings from a dict.
        """
        with self._lock:
            data = self.repo.load_all()
            settings = self._data_to_settings(data)
            for k, v in updates.items():
                if hasattr(settings, k):
                    setattr(settings, k, v)
                else:
                    log.warning(f"Unknown setting key: {k!r}")
            new_data = self._settings_to_data(settings)
            self.repo.save_all(new_data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_settings_manager: Optional[ACSettingsManager] = None


def get_settings_manager() -> ACSettingsManager:
    """Return the process-wide :class:`ACSettingsManager` singleton."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = ACSettingsManager()
    return _settings_manager


if __name__ == "__main__":
    manager = get_settings_manager()
    manager.update_multiple_settings({
        'target_temp': 30.2
    })
    for k, v in manager.load_settings().items():
        print(f"  {k}: {v}")
