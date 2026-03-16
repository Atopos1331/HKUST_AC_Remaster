import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple

from powers.utils.logger import log
from powers.auth.auth import login

from powers.utils.config import Web


class AirConditionerAPI:
    """HTTP client for the HKUST prepaid AC portal API.

    Handles authentication via :func:`~powers.auth.auth.login`, automatic
    token refresh on expiry, and retries on transient failures.
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.token: str = ""
        self.info: dict = {}
        log.info("Authenticating the AC portal...")
        self.authenticate()

    def authenticate(self, no_cookie: bool = False) -> None:
        """Obtain a fresh bearer token, escalating to no-cookie mode after 3 failures."""
        for i in range(5):
            try:
                self.token, self.info = login(no_cookie=no_cookie)
                return
            except Exception as e:
                log.error(f"Authentication failed: {e} (attempt {i + 1}/5)")
                if i == 2:
                    no_cookie = True
                    log.warning("Switching to no-cookie mode for re-authentication.")
                    
        log.error("Authentication failed: max retries reached.")
        raise RuntimeError("Failed to authenticate after 5 attempts.")

    def check_token(self) -> bool:
        """Return True if the stored token is still accepted by the API."""
        try:
            r = self.session.get(
                f"{Web.Web.API_BASE}/prepaid/ac-balance",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            return r.json()["meta"]["message"] == "Success"
        except Exception:
            return False

    def _api_request(self, url: str, data: Optional[dict] = None,
                     neglect_message_check: bool = False) -> dict:
        """Send a GET or POST request with automatic token refresh and retries.

        Args:
            url:                    Full endpoint URL.
            data:                   JSON body – triggers POST when provided.
            neglect_message_check:  Skip the ``meta.message == 'Success'`` check.

        Returns:
            Parsed JSON response dict.

        Raises:
            Exception: When all 5 attempts are exhausted.
        """
        for attempt in range(5):
            try:
                headers = {"Authorization": f"Bearer {self.token}"}
                method = "POST" if data else "GET"
                resp = self.session.request(method, url, headers=headers, json=data)
                result = resp.json()

                if result["meta"]["message"] == "Invalid Bearer Token.":
                    log.warning("Token expired – re-authenticating.")
                    self.authenticate()
                    continue

                if not neglect_message_check and result["meta"]["message"] != "Success":
                    raise ValueError(result["meta"]["message"])

                return result["data"] if data is None else result

            except Exception as e:
                log.error(f"API request failed: {e} (attempt {attempt + 1}/5)")

        raise RuntimeError("Max retries reached for API request.")

    # ------------------------------------------------------------------
    # Read-only endpoints
    # ------------------------------------------------------------------

    def get_balance(self) -> Tuple[int, int]:
        """Return ``(balance_minutes, total_paid_minutes)``."""
        d = self._api_request(f"{Web.API_BASE}/prepaid/ac-balance")["ac_data"]
        return int(d["balance"]), int(d["total_paid"])

    def get_status(self) -> Tuple[float, float, float, float]:
        """Return ``(voltage_V, current_A, active_power_W, energy_Wh)``."""
        d = self._api_request(f"{Web.API_BASE}/prepaid/ac-status")["ac_status"]
        return (
            float(d["V"]),
            float(d["I"]),
            float(d["P"]) * 1000,
            float(d["kWhImport"]) * 1000,
        )

    def get_ac_is_on(self) -> bool:
        """Return True when the AC is actively consuming power (P > 0)."""
        return self.get_status()[2] > 1e-5

    def get_timer(self, bjt: bool = True) -> Optional[datetime]:
        """Return the scheduled turn-off time, or None if no timer is set.

        Args:
            bjt: Convert the UTC timestamp to Beijing/HK time (UTC+8) when True.
        """
        data = self._api_request(f"{Web.API_BASE}/prepaid/ac-timer")["ac_timer"]
        if data == 0:
            return None
        dt = (
            datetime.fromisoformat(data.replace("Z", "+00:00"))
            .astimezone(None)
            .replace(tzinfo=None)
        )
        return dt if bjt else dt - timedelta(hours=8)

    def get_power_consumption(self, period: str) -> dict:
        """Fetch power-consumption summary for the given *period* ('daily'/'weekly'/'monthly')."""
        return self._api_request(
            f"{Web.API_BASE}/dashboard/power-consumption-summary"
            f"?period={period}&charge_type=prepaid"
        )["power_consumption_summary"]

    def get_info(self) -> dict:
        """Return a flat dict with the student's account details."""
        s = self.info["student"]
        return {
            "sid":   s["id"],
            "name":  s["name"],
            "email": s["email"],
            "hall":  s["bldg_short_nam"],
            "room":  s["bldg_apt_room_nbr"],
            "bed":   s["bldg_room_bed_nbr"],
        }

    # ------------------------------------------------------------------
    # Write endpoints
    # ------------------------------------------------------------------

    def set_status(self, status: bool) -> int:
        """Toggle the AC on or off.

        Returns:
            0  – successfully changed,
            -1 – state was already as requested,
            1  – server reported a failure.
        """
        data = {"toggle": {"status": 1 if status else 0}}
        result = self._api_request(
            f"{Web.API_BASE}/prepaid/toggle-status", data, neglect_message_check=True
        )
        if "already turned" in result["meta"]["message"]:
            return -1
        return 0 if result["meta"]["code"] == 200 else 1

    def set_timer(self, off_time: datetime, bjt: bool = True) -> bool:
        """Set a scheduled turn-off time.

        Args:
            off_time: The desired shut-off time.
            bjt:      Treat *off_time* as Beijing/HK time (subtract 8 h for UTC).

        Returns:
            True on success.
        """
        t = off_time - timedelta(hours=8) if bjt else off_time
        data = {"ac_timer": {"timer": t.isoformat(timespec="milliseconds") + "Z"}}
        r = self._api_request(f"{Web.API_BASE}/prepaid/ac-timer", data)
        return r["meta"]["code"] == 200


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_api: Optional[AirConditionerAPI] = None


def get_ac_api() -> AirConditionerAPI:
    """Return the process-wide :class:`AirConditionerAPI` singleton."""
    global _api
    if _api is None:
        _api = AirConditionerAPI()
    return _api


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    api = get_ac_api()
    balance, total_paid = api.get_balance()
    print(f"Balance: {balance} min  |  Total paid: {total_paid} min")
    _, _, power, _ = api.get_status()
    print(f"AC is {'ON' if power > 0 else 'OFF'}")
    print(f"Info: {api.get_info()}")