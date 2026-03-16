import threading
import time
from datetime import datetime
from typing import Any, Dict

from powers.auth.ac_api import get_ac_api
from powers.data.global_state import (
    add_recent_decision,
    read_heat_index,
    write_ac_is_on,
    write_indoor_climate,
    write_last_switch,
)
from powers.data.recorder import get_recorder
from powers.data.settings import get_settings_manager
from powers.discord_bot import DiscordBot
from powers.io.thermometer import get_climate
from powers.qq_bot import QQBot
from powers.services.control_service import ControlService
from powers.utils.config import Config
from powers.utils.logger import log

ENABLE_QQ_BOT = True
ENABLE_DISCORD_BOT = True

TEMPERATURE_PULL_INTERVAL = Config.TEMPERATURE_PULL_INTERVAL
CONTROL_CYCLE_INTERVAL = Config.CONTROL_CYCLE_INTERVAL
WAIT_ON_SWITCH_OFF = Config.WAIT_ON_SWITCH_OFF
WAIT_ON_BALANCE_LOW = Config.WAIT_ON_BALANCE_LOW
RECORD_INTERVAL = Config.RECORD_INTERVAL
WEATHER_POLL_INTERVAL = Config.WEATHER_POLL_INTERVAL

stop_event = threading.Event()


def _get_api():
    return get_ac_api()


def _get_recorder():
    return get_recorder()


def recorder_thread() -> None:
    """Periodically persist indoor sensor and electrical readings."""
    recorder = _get_recorder()
    log.info("Data recorder thread started.")
    while not stop_event.is_set():
        try:
            recorder.record()
            log.info("Recorded one snapshot of run-time data.")
        except Exception as e:
            log.warning(f"Failed to record run-time data: {e}")
        if stop_event.wait(RECORD_INTERVAL):
            break
    log.info("Data recorder thread exited.")


def weather_recorder_thread() -> None:
    """Periodically fetch and persist outdoor weather data."""
    recorder = _get_recorder()
    log.info("Weather recorder thread started.")
    while not stop_event.is_set():
        try:
            recorder.record_outdoor()
            log.info("Recorded one snapshot of outdoor weather.")
        except Exception as e:
            log.warning(f"Failed to fetch outdoor weather: {e}")
        if stop_event.wait(WEATHER_POLL_INTERVAL):
            break
    log.info("Weather recorder thread exited.")


def sensor_monitoring_thread() -> None:
    """Continuously read the indoor sensor and update global state."""
    log.info("Indoor climate sensor thread started.")
    while not stop_event.is_set():
        try:
            reading = get_climate()
            write_indoor_climate(reading.temperature, reading.humidity)
            log.info(
                f"Indoor climate: temperature={reading.temperature:.2f} C, "
                f"humidity={reading.humidity:.2f} %, "
                f"heat_index={read_heat_index():.2f} C"
            )
        except Exception as e:
            log.warning(f"Failed to read indoor climate: {e}")
        if stop_event.wait(TEMPERATURE_PULL_INTERVAL):
            break
    log.info("Indoor climate sensor thread exited.")


def control_logic_thread() -> None:
    """Run the AC control loop: decide, apply, wait, repeat."""
    log.info("AC control logic thread started.")
    settings_manager = get_settings_manager()
    api = _get_api()

    write_ac_is_on(api.get_ac_is_on())
    write_last_switch(datetime(1970, 1, 1))

    while not stop_event.is_set():
        try:
            settings = settings_manager.load()
            switch = settings.switch

            if switch == 0:
                log.info("Master switch is OFF; skipping control cycle.")
                stop_event.wait(WAIT_ON_SWITCH_OFF)
                continue

            balance = api.get_balance()[0]
            if balance <= 0:
                log.info("Insufficient balance; skipping control cycle.")
                stop_event.wait(WAIT_ON_BALANCE_LOW)
                continue

            log.info(f"Balance: {balance} min")

            action, next_time, info = ControlService.decide()
            log.info(f"Decision: action={action} next={next_time} reason={info.get('reason')}")
            add_recent_decision(action, next_time, info or {})
            ControlService.action(action, next_time, info)

            stop_event.wait(CONTROL_CYCLE_INTERVAL)

        except Exception as e:
            log.error(f"Control logic error: {e}")
            import traceback

            traceback.print_exc()
            stop_event.wait(2)

    log.info("AC control logic thread exited.")


def start_runtime() -> Dict[str, Any]:
    """Start all worker threads and optional bot connections."""
    if stop_event.is_set():
        stop_event.clear()

    log.info("Starting AC controller...")

    qq_bot = QQBot() if ENABLE_QQ_BOT else None
    discord_bot = DiscordBot() if ENABLE_DISCORD_BOT else None

    if qq_bot is not None:
        qq_bot.start()
    if discord_bot is not None:
        discord_bot.start()

    sensor_thread = threading.Thread(target=sensor_monitoring_thread, daemon=False, name="sensor-thread")
    control_thread = threading.Thread(target=control_logic_thread, daemon=False, name="control-thread")
    record_thread = threading.Thread(target=recorder_thread, daemon=False, name="record-thread")
    weather_thread = threading.Thread(target=weather_recorder_thread, daemon=False, name="weather-thread")

    sensor_thread.start()
    control_thread.start()
    record_thread.start()
    weather_thread.start()

    log.info("All threads started.")
    return {
        "qq_bot": qq_bot,
        "discord_bot": discord_bot,
        "threads": [sensor_thread, control_thread, record_thread, weather_thread],
    }


def shutdown_runtime(runtime: Dict[str, Any]) -> None:
    """Stop all worker threads and bot connections."""
    stop_event.set()
    log.info("Waiting for threads to finish...")
    for thread in runtime["threads"]:
        thread.join()
    if runtime["qq_bot"] is not None:
        runtime["qq_bot"].stop()
    if runtime["discord_bot"] is not None:
        runtime["discord_bot"].stop()
    log.info("Shutdown complete.")


def main() -> None:
    runtime = start_runtime()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Interrupt received; shutting down...")
    finally:
        shutdown_runtime(runtime)


if __name__ == "__main__":
    main()
