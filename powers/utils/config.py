import inspect
import json
import os
import sys

_CREDS_FILES = ("creds.json", "creds/credentials.json")


def _load_credentials() -> dict:
    for creds_file in _CREDS_FILES:
        if os.path.exists(creds_file):
            with open(creds_file, encoding="utf-8") as handle:
                return json.load(handle)
    raise FileNotFoundError(
        "Credentials file not found. Create 'creds.json' or "
        "'creds/credentials.json' based on 'creds/credentials.example.json'."
    )


_creds: dict = _load_credentials()


class WebConfig:
    STATE_FILE = "data/state.json"
    TARGET_URL = "https://w5.ab.ust.hk/njggt/app/"
    API_BASE = "https://w5.ab.ust.hk/njggt/api/app"


class AuthConfig:
    EMAIL: str = _creds["email"]
    PASSWORD: str = _creds["password"]
    MICROSOFT_SECRET: str = _creds["microsoft_secret"]


class BotConfig:
    APPID: str = _creds["qq_app_id"]
    SECRET: str = _creds["qq_secret"]
    DISCORD_TOKEN: str = _creds.get("discord_token", "")
    COMMAND_LANGUAGE: str = _creds.get("command_language", _creds.get("bot_language", "zh"))


class RuntimeConfig:
    TEMPERATURE_PULL_INTERVAL: int = 10
    CONTROL_CYCLE_INTERVAL: int = 30
    WAIT_ON_SWITCH_OFF: int = 60
    WAIT_ON_BALANCE_LOW: int = 120
    RECORD_INTERVAL: int = 15
    WEATHER_POLL_INTERVAL: int = 180


class ControlConfig:
    COOLDOWN_TIME: int = 300
    DEFAULT_ONTIME: int = 300
    DEFAULT_OFFTIME: int = 1100
    TEMP_THRESHOLD_HIGH: float = 0.5
    TEMP_THRESHOLD_LOW: float = 0.3
    TEMP_LOCK_MAX_DURATION: int = 24 * 3600


class StorageConfig:
    SETTINGS_JSON_PATH: str = "data/settings.json"
    DB_PATH: str = "data/ac_history.sqlite"
    FIGURE_DIR: str = "figure"
    MAX_RECORDS: int = 50


class GeographyConfig:
    LATITUDE: float = 22.338808403679376
    LONGITUDE: float = 114.26581766847202


class AppConfig:
    BOT_LANGUAGE: str = BotConfig.COMMAND_LANGUAGE

    TEMPERATURE_PULL_INTERVAL: int = RuntimeConfig.TEMPERATURE_PULL_INTERVAL
    CONTROL_CYCLE_INTERVAL: int = RuntimeConfig.CONTROL_CYCLE_INTERVAL
    WAIT_ON_SWITCH_OFF: int = RuntimeConfig.WAIT_ON_SWITCH_OFF
    WAIT_ON_BALANCE_LOW: int = RuntimeConfig.WAIT_ON_BALANCE_LOW
    RECORD_INTERVAL: int = RuntimeConfig.RECORD_INTERVAL
    WEATHER_POLL_INTERVAL: int = RuntimeConfig.WEATHER_POLL_INTERVAL

    COOLDOWN_TIME: int = ControlConfig.COOLDOWN_TIME
    DEFAULT_ONTIME: int = ControlConfig.DEFAULT_ONTIME
    DEFAULT_OFFTIME: int = ControlConfig.DEFAULT_OFFTIME
    TEMP_THRESHOLD_HIGH: float = ControlConfig.TEMP_THRESHOLD_HIGH
    TEMP_THRESHOLD_LOW: float = ControlConfig.TEMP_THRESHOLD_LOW
    TEMP_LOCK_MAX_DURATION: int = ControlConfig.TEMP_LOCK_MAX_DURATION

    SETTINGS_JSON_PATH: str = StorageConfig.SETTINGS_JSON_PATH
    DB_PATH: str = StorageConfig.DB_PATH
    FIGURE_DIR: str = StorageConfig.FIGURE_DIR
    MAX_RECORDS: int = StorageConfig.MAX_RECORDS


class RecorderConfig:
    DB_PATH: str = StorageConfig.DB_PATH
    LATITUDE: float = GeographyConfig.LATITUDE
    LONGITUDE: float = GeographyConfig.LONGITUDE


# Backward-compatible aliases
Web = WebConfig
Auth = AuthConfig
Bot = BotConfig
Runtime = RuntimeConfig
Control = ControlConfig
Storage = StorageConfig
Geography = GeographyConfig
Config = AppConfig
Recorder = RecorderConfig


if __name__ == "__main__":
    mod = sys.modules[__name__]

    def _is_config_class(obj: object) -> bool:
        return inspect.isclass(obj) and obj.__module__ == mod.__name__  # type: ignore[attr-defined]

    print("=== Configuration ===")
    for name, obj in vars(mod).items():
        if _is_config_class(obj):
            attrs = {
                key: value
                for key, value in vars(obj).items()
                if key.isupper() and not key.startswith("_") and not inspect.isroutine(value)
            }
            print(f"\n{name}:")
            for key, value in attrs.items():
                print(f"  {key} = {value}")
