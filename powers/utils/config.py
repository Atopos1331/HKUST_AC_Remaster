from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
import threading
from typing import Any


_CREDS_FILES = ("creds.json", "creds/credentials.json")
_credentials_lock = threading.Lock()
_credentials: "Credentials | None" = None


@dataclass(frozen=True, slots=True)
class Credentials:
    email: str
    password: str
    microsoft_secret: str
    qq_app_id: str
    qq_secret: str
    discord_token: str = ""
    command_language: str = "zh"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Credentials":
        return cls(
            email=str(data["email"]),
            password=str(data["password"]),
            microsoft_secret=str(data["microsoft_secret"]),
            qq_app_id=str(data["qq_app_id"]),
            qq_secret=str(data["qq_secret"]),
            discord_token=str(data.get("discord_token", "")),
            command_language=str(data.get("command_language", data.get("bot_language", "zh"))),
        )


def _load_credentials_from_disk() -> Credentials:
    for creds_file in _CREDS_FILES:
        path = Path(creds_file)
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                return Credentials.from_dict(json.load(handle))
    raise FileNotFoundError(
        "Credentials file not found. Create 'creds.json' or "
        "'creds/credentials.json' based on 'creds/credentials.example.json'."
    )


def get_credentials() -> Credentials:
    global _credentials
    if _credentials is None:
        with _credentials_lock:
            if _credentials is None:
                _credentials = _load_credentials_from_disk()
    return _credentials


def try_get_credentials() -> Credentials | None:
    try:
        return get_credentials()
    except FileNotFoundError:
        return None


@dataclass(frozen=True, slots=True)
class WebConfig:
    STATE_FILE: str = "data/state.json"
    TARGET_URL: str = "https://w5.ab.ust.hk/njggt/app/"
    API_BASE: str = "https://w5.ab.ust.hk/njggt/api/app"


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    TEMPERATURE_PULL_INTERVAL: int = 10
    CONTROL_CYCLE_INTERVAL: int = 30
    WAIT_ON_SWITCH_OFF: int = 60
    WAIT_ON_BALANCE_LOW: int = 120
    RECORD_INTERVAL: int = 15
    WEATHER_POLL_INTERVAL: int = 180


@dataclass(frozen=True, slots=True)
class ControlConfig:
    COOLDOWN_TIME: int = 300
    DEFAULT_ONTIME: int = 300
    DEFAULT_OFFTIME: int = 1100
    TEMP_THRESHOLD_HIGH: float = 0.5
    TEMP_THRESHOLD_LOW: float = 0.3
    TEMP_LOCK_MAX_DURATION: int = 24 * 3600


@dataclass(frozen=True, slots=True)
class StorageConfig:
    SETTINGS_JSON_PATH: str = "data/settings.json"
    DB_PATH: str = "data/ac_history.sqlite"
    FIGURE_DIR: str = "figure"
    MAX_RECORDS: int = 50


@dataclass(frozen=True, slots=True)
class GeographyConfig:
    LATITUDE: float = 22.338808403679376
    LONGITUDE: float = 114.26581766847202


class AuthConfig:
    @property
    def EMAIL(self) -> str:
        return get_credentials().email

    @property
    def PASSWORD(self) -> str:
        return get_credentials().password

    @property
    def MICROSOFT_SECRET(self) -> str:
        return get_credentials().microsoft_secret


class BotConfig:
    @property
    def APPID(self) -> str:
        creds = try_get_credentials()
        return creds.qq_app_id if creds is not None else ""

    @property
    def SECRET(self) -> str:
        creds = try_get_credentials()
        return creds.qq_secret if creds is not None else ""

    @property
    def DISCORD_TOKEN(self) -> str:
        creds = try_get_credentials()
        return creds.discord_token if creds is not None else ""

    @property
    def COMMAND_LANGUAGE(self) -> str:
        creds = try_get_credentials()
        return creds.command_language if creds is not None else "zh"


class AppConfig:
    @property
    def BOT_LANGUAGE(self) -> str:
        return Bot.COMMAND_LANGUAGE

    @property
    def TEMPERATURE_PULL_INTERVAL(self) -> int:
        return Runtime.TEMPERATURE_PULL_INTERVAL

    @property
    def CONTROL_CYCLE_INTERVAL(self) -> int:
        return Runtime.CONTROL_CYCLE_INTERVAL

    @property
    def WAIT_ON_SWITCH_OFF(self) -> int:
        return Runtime.WAIT_ON_SWITCH_OFF

    @property
    def WAIT_ON_BALANCE_LOW(self) -> int:
        return Runtime.WAIT_ON_BALANCE_LOW

    @property
    def RECORD_INTERVAL(self) -> int:
        return Runtime.RECORD_INTERVAL

    @property
    def WEATHER_POLL_INTERVAL(self) -> int:
        return Runtime.WEATHER_POLL_INTERVAL

    @property
    def COOLDOWN_TIME(self) -> int:
        return Control.COOLDOWN_TIME

    @property
    def DEFAULT_ONTIME(self) -> int:
        return Control.DEFAULT_ONTIME

    @property
    def DEFAULT_OFFTIME(self) -> int:
        return Control.DEFAULT_OFFTIME

    @property
    def TEMP_THRESHOLD_HIGH(self) -> float:
        return Control.TEMP_THRESHOLD_HIGH

    @property
    def TEMP_THRESHOLD_LOW(self) -> float:
        return Control.TEMP_THRESHOLD_LOW

    @property
    def TEMP_LOCK_MAX_DURATION(self) -> int:
        return Control.TEMP_LOCK_MAX_DURATION

    @property
    def SETTINGS_JSON_PATH(self) -> str:
        return Storage.SETTINGS_JSON_PATH

    @property
    def DB_PATH(self) -> str:
        return Storage.DB_PATH

    @property
    def FIGURE_DIR(self) -> str:
        return Storage.FIGURE_DIR

    @property
    def MAX_RECORDS(self) -> int:
        return Storage.MAX_RECORDS


class RecorderConfig:
    @property
    def DB_PATH(self) -> str:
        return Storage.DB_PATH

    @property
    def LATITUDE(self) -> float:
        return Geography.LATITUDE

    @property
    def LONGITUDE(self) -> float:
        return Geography.LONGITUDE


Web = WebConfig()
Runtime = RuntimeConfig()
Control = ControlConfig()
Storage = StorageConfig()
Geography = GeographyConfig()
Auth = AuthConfig()
Bot = BotConfig()
Config = AppConfig()
Recorder = RecorderConfig()


def dump_config_sections() -> dict[str, dict[str, Any]]:
    return {
        "Web": asdict(Web),
        "Runtime": asdict(Runtime),
        "Control": asdict(Control),
        "Storage": asdict(Storage),
        "Geography": asdict(Geography),
        "Recorder": {
            "DB_PATH": Recorder.DB_PATH,
            "LATITUDE": Recorder.LATITUDE,
            "LONGITUDE": Recorder.LONGITUDE,
        },
        "Bot": {
            "APPID": Bot.APPID,
            "SECRET": Bot.SECRET,
            "DISCORD_TOKEN": Bot.DISCORD_TOKEN,
            "COMMAND_LANGUAGE": Bot.COMMAND_LANGUAGE,
        },
        "Auth": {
            "EMAIL": Auth.EMAIL,
            "PASSWORD": Auth.PASSWORD,
            "MICROSOFT_SECRET": Auth.MICROSOFT_SECRET,
        },
        "Config": {
            "BOT_LANGUAGE": Config.BOT_LANGUAGE,
            "TEMPERATURE_PULL_INTERVAL": Config.TEMPERATURE_PULL_INTERVAL,
            "CONTROL_CYCLE_INTERVAL": Config.CONTROL_CYCLE_INTERVAL,
            "WAIT_ON_SWITCH_OFF": Config.WAIT_ON_SWITCH_OFF,
            "WAIT_ON_BALANCE_LOW": Config.WAIT_ON_BALANCE_LOW,
            "RECORD_INTERVAL": Config.RECORD_INTERVAL,
            "WEATHER_POLL_INTERVAL": Config.WEATHER_POLL_INTERVAL,
            "COOLDOWN_TIME": Config.COOLDOWN_TIME,
            "DEFAULT_ONTIME": Config.DEFAULT_ONTIME,
            "DEFAULT_OFFTIME": Config.DEFAULT_OFFTIME,
            "TEMP_THRESHOLD_HIGH": Config.TEMP_THRESHOLD_HIGH,
            "TEMP_THRESHOLD_LOW": Config.TEMP_THRESHOLD_LOW,
            "TEMP_LOCK_MAX_DURATION": Config.TEMP_LOCK_MAX_DURATION,
            "SETTINGS_JSON_PATH": Config.SETTINGS_JSON_PATH,
            "DB_PATH": Config.DB_PATH,
            "FIGURE_DIR": Config.FIGURE_DIR,
            "MAX_RECORDS": Config.MAX_RECORDS,
        },
    }


if __name__ == "__main__":
    print("=== Configuration ===")
    for section_name, section in dump_config_sections().items():
        print(f"\n{section_name}:")
        for key, value in section.items():
            print(f"  {key} = {value}")
