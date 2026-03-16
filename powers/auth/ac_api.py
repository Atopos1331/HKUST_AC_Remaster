from __future__ import annotations

from datetime import datetime, timedelta
import threading
from typing import Any, Optional, Tuple

import requests

from powers.auth.auth import login
from powers.utils.config import Web
from powers.utils.logger import log


class AirConditionerAPI:
    """Thread-safe HKUST prepaid AC portal client."""

    def __init__(self) -> None:
        self._local = threading.local()
        self._auth_lock = threading.RLock()
        self._token = ""
        self._info: dict[str, Any] = {}
        self._auth_generation = 0
        log.info("Authenticating the AC portal...")
        self.authenticate()

    def _get_session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def _get_auth_snapshot(self) -> tuple[str, dict[str, Any], int]:
        with self._auth_lock:
            return self._token, dict(self._info), self._auth_generation

    def _authenticate_locked(self, no_cookie: bool = False) -> None:
        for attempt in range(5):
            try:
                token, info = login(no_cookie=no_cookie)
                self._token = token
                self._info = dict(info)
                self._auth_generation += 1
                return
            except Exception as exc:
                log.error(f"Authentication failed: {exc} (attempt {attempt + 1}/5)")
                if attempt == 2:
                    no_cookie = True
                    log.warning("Switching to no-cookie mode for re-authentication.")
        log.error("Authentication failed: max retries reached.")
        raise RuntimeError("Failed to authenticate after 5 attempts.")

    def authenticate(self, no_cookie: bool = False) -> None:
        with self._auth_lock:
            self._authenticate_locked(no_cookie=no_cookie)

    def _refresh_token(self, seen_generation: int) -> None:
        with self._auth_lock:
            if self._auth_generation != seen_generation and self._token:
                return
            self._authenticate_locked()

    def check_token(self) -> bool:
        token, _, _ = self._get_auth_snapshot()
        try:
            response = self._get_session().get(
                f"{Web.API_BASE}/prepaid/ac-balance",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            payload = response.json()
            return payload.get("meta", {}).get("message") == "Success"
        except Exception:
            return False

    def _api_request(
        self,
        url: str,
        data: Optional[dict[str, Any]] = None,
        neglect_message_check: bool = False,
    ) -> dict[str, Any]:
        for attempt in range(5):
            token, _, generation = self._get_auth_snapshot()
            try:
                response = self._get_session().request(
                    "POST" if data is not None else "GET",
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    json=data,
                    timeout=15,
                )
                result = response.json()
                message = result.get("meta", {}).get("message")

                if message == "Invalid Bearer Token.":
                    log.warning("Token expired; re-authenticating.")
                    self._refresh_token(generation)
                    continue

                if not neglect_message_check and message != "Success":
                    raise ValueError(message)

                return result["data"] if data is None else result
            except Exception as exc:
                log.error(f"API request failed: {exc} (attempt {attempt + 1}/5)")

        raise RuntimeError("Max retries reached for API request.")

    def get_balance(self) -> Tuple[int, int]:
        data = self._api_request(f"{Web.API_BASE}/prepaid/ac-balance")["ac_data"]
        return int(data["balance"]), int(data["total_paid"])

    def get_status(self) -> Tuple[float, float, float, float]:
        data = self._api_request(f"{Web.API_BASE}/prepaid/ac-status")["ac_status"]
        return (
            float(data["V"]),
            float(data["I"]),
            float(data["P"]) * 1000,
            float(data["kWhImport"]) * 1000,
        )

    def get_ac_is_on(self) -> bool:
        return self.get_status()[2] > 1e-5

    def get_timer(self, bjt: bool = True) -> Optional[datetime]:
        data = self._api_request(f"{Web.API_BASE}/prepaid/ac-timer")["ac_timer"]
        if data == 0:
            return None
        dt = datetime.fromisoformat(data.replace("Z", "+00:00")).astimezone(None).replace(tzinfo=None)
        return dt if bjt else dt - timedelta(hours=8)

    def get_power_consumption(self, period: str) -> dict[str, Any]:
        return self._api_request(
            f"{Web.API_BASE}/dashboard/power-consumption-summary"
            f"?period={period}&charge_type=prepaid"
        )["power_consumption_summary"]

    def get_info(self) -> dict[str, Any]:
        _, info, _ = self._get_auth_snapshot()
        student = info["student"]
        return {
            "sid": student["id"],
            "name": student["name"],
            "email": student["email"],
            "hall": student["bldg_short_nam"],
            "room": student["bldg_apt_room_nbr"],
            "bed": student["bldg_room_bed_nbr"],
        }

    def set_status(self, status: bool) -> int:
        data = {"toggle": {"status": 1 if status else 0}}
        result = self._api_request(
            f"{Web.API_BASE}/prepaid/toggle-status",
            data,
            neglect_message_check=True,
        )
        message = result.get("meta", {}).get("message", "")
        if "already turned" in message:
            return -1
        return 0 if result.get("meta", {}).get("code") == 200 else 1

    def set_timer(self, off_time: datetime, bjt: bool = True) -> bool:
        timer_value = off_time - timedelta(hours=8) if bjt else off_time
        payload = {"ac_timer": {"timer": timer_value.isoformat(timespec="milliseconds") + "Z"}}
        result = self._api_request(f"{Web.API_BASE}/prepaid/ac-timer", payload)
        return result["meta"]["code"] == 200


_api: AirConditionerAPI | None = None
_api_lock = threading.Lock()


def get_ac_api() -> AirConditionerAPI:
    global _api
    if _api is None:
        with _api_lock:
            if _api is None:
                _api = AirConditionerAPI()
    return _api


if __name__ == "__main__":
    api = get_ac_api()
    balance, total_paid = api.get_balance()
    print(f"Balance: {balance} min  |  Total paid: {total_paid} min")
    _, _, power, _ = api.get_status()
    print(f"AC is {'ON' if power > 0 else 'OFF'}")
    print(f"Info: {api.get_info()}")
