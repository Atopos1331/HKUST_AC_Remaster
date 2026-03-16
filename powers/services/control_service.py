from datetime import datetime, timedelta
from typing import Literal, Optional, Tuple

from powers.auth.ac_api import get_ac_api
from powers.data.global_state import (
    add_recent_applied,
    read_ac_is_on,
    read_indoor_climate,
    read_last_switch,
    write_ac_is_on,
    write_indoor_climate,
    write_last_switch,
)
from powers.data.settings import get_settings_manager
from powers.utils.logger import log


def _datetime_from_iso(iso_string: str, default: datetime = datetime(1970, 1, 1)) -> datetime:
    """Convert ISO string to datetime, with fallback to ``default``."""
    try:
        return datetime.fromisoformat(iso_string)
    except Exception:
        return default




def _get_api():
    return get_ac_api()


class ControlService:
    """Stateless AC control logic: ``decide`` plus ``action``."""

    @staticmethod
    def decide() -> Tuple[Optional[Literal["open", "close"]], Optional[datetime], dict]:
        """Determine whether to change the AC state."""
        settings = get_settings_manager().load()
        now = datetime.now()
        ac_is_on = read_ac_is_on()
        current_state_action: Literal["open", "close"] = "open" if ac_is_on else "close"

        lock_status = settings.lock_status
        lock_end_time = _datetime_from_iso(settings.lock_end_time)
        if now < lock_end_time:
            mismatch = ac_is_on != lock_status
            reason = "lock_active_state_mismatch" if mismatch else "lock_active_state_match"
            return ("open" if lock_status else "close"), lock_end_time, {"reason": reason}

        control_mode = settings.control_mode
        last_switch = read_last_switch()

        if control_mode == "scheduler":
            ontime = settings.ontime
            offtime = settings.offtime
            elapsed = (now - last_switch).total_seconds()

            if ac_is_on:
                if elapsed >= ontime:
                    return "close", now + timedelta(seconds=offtime), {"reason": "scheduler_close"}
                return "open", last_switch + timedelta(seconds=ontime), {"reason": "scheduler_on_wait"}

            if elapsed >= offtime:
                return "open", now + timedelta(seconds=ontime), {"reason": "scheduler_open"}
            return "close", last_switch + timedelta(seconds=offtime), {"reason": "scheduler_off_wait"}

        if control_mode == "temperature":
            cooldown_secs = settings.cooldown_time
            cooldown_delta = timedelta(seconds=cooldown_secs)
            if last_switch + cooldown_delta > now:
                return current_state_action, last_switch + cooldown_delta, {"reason": "cooldown"}

            basis = settings.temperature_control_basis
            climate = read_indoor_climate()
            current_value = climate.temperature if basis == "temperature" else climate.heat_index
            target_value = settings.target_temp

            if current_value is None:
                return current_state_action, None, {"reason": f"{basis}_unavailable", "basis": basis}

            threshold_high = settings.temp_threshold_high
            threshold_low = settings.temp_threshold_low
            metric_key = "current_temp" if basis == "temperature" else "current_heat_index"

            if current_value < target_value - threshold_low and ac_is_on:
                return "close", now + cooldown_delta, {
                    "reason": f"{basis}_below_threshold",
                    metric_key: current_value,
                    "basis": basis,
                    "target": target_value,
                }
            if current_value > target_value + threshold_high and not ac_is_on:
                return "open", now + cooldown_delta, {
                    "reason": f"{basis}_above_threshold",
                    metric_key: current_value,
                    "basis": basis,
                    "target": target_value,
                }
            return current_state_action, now + cooldown_delta, {
                "reason": "keep_current",
                metric_key: current_value,
                "basis": basis,
                "target": target_value,
            }

        return None, None, {"reason": "unknown_mode"}

    @staticmethod
    def action(
        action: Optional[Literal["open", "close"]],
        next_time: Optional[datetime] = None,
        info: Optional[dict] = None,
    ) -> None:
        """Execute an AC state change and sync the off-timer when needed."""
        api = _get_api()
        if action:
            res = api.set_status(action == "open")
            if res == 0:
                switched_at = datetime.now()
                write_ac_is_on(action == "open")
                write_last_switch(switched_at)
                add_recent_applied(action, next_time, info or {})
                log.info(f"AC {'turned on' if action == 'open' else 'turned off'} successfully")
            elif res == -1:
                log.info(f"AC state unchanged; already {'on' if action == 'open' else 'off'}")
            else:
                log.warning(f"AC {'on' if action == 'open' else 'off'} command failed (code {res})")

        if action == "open":
            timer = api.get_timer()
            if next_time and (not timer or abs((timer - next_time).total_seconds()) > 3):
                api.set_timer(next_time)
                log.info(f"AC off-timer updated to {next_time}")


if __name__ == "__main__":
    api = _get_api()
    write_ac_is_on(api.get_ac_is_on())
    write_indoor_climate(25.0, 60.0)
    decided_action, decided_next_time, decided_info = ControlService.decide()
    print(f"Decision: action={decided_action}, next_time={decided_next_time}, info={decided_info}")
    ControlService.action(decided_action, decided_next_time, decided_info)
