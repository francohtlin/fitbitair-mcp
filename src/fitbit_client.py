"""
Google Health API wrapper.

Endpoint pattern (verified via Sprint 0):
  GET  https://health.googleapis.com/v4/users/me/dataTypes/{type}/dataPoints
  POST https://health.googleapis.com/v4/users/me/dataTypes/{type}/dataPoints:dailyRollUp

Daily types (one aggregate per day): daily-heart-rate-variability,
  daily-resting-heart-rate, daily-respiratory-rate,
  daily-sleep-temperature-derivations, daily-oxygen-saturation

Session/sample types: sleep, heart-rate, weight

Steps: only POST :dailyRollUp is supported (GET returns 400).
Heart rate: GET requires physical_time filter + pagination for the sleep window.
"""

import datetime
import logging
from typing import Any

import google.auth.transport.requests
import requests

from src.auth import get_credentials
from src.config import GOOGLE_HEALTH_BASE_URL

log = logging.getLogger(__name__)


class GoogleHealthClient:
    def __init__(self) -> None:
        self._session = requests.Session()

    def _auth_header(self) -> dict[str, str]:
        creds = get_credentials()
        if not creds.valid or not creds.token:
            creds.refresh(google.auth.transport.requests.Request())
        return {"Authorization": f"Bearer {creds.token}"}

    def _get(self, data_type: str) -> dict[str, Any] | None:
        url = f"{GOOGLE_HEALTH_BASE_URL}/users/me/dataTypes/{data_type}/dataPoints"
        try:
            resp = self._session.get(url, headers=self._auth_header())
            resp.raise_for_status()
            data = resp.json()
            log.debug("%s → %d points", data_type, len(data.get("dataPoints", [])))
            return data
        except requests.HTTPError as e:
            log.warning("%s → HTTP %s", data_type, e.response.status_code)
            return None
        except Exception as e:
            log.warning("%s → %s", data_type, e)
            return None

    def _post_daily_rollup(self, data_type: str, date: datetime.date) -> dict[str, Any] | None:
        url = f"{GOOGLE_HEALTH_BASE_URL}/users/me/dataTypes/{data_type}/dataPoints:dailyRollUp"
        next_day = date + datetime.timedelta(days=1)
        body = {
            "range": {
                "start": {"date": {"year": date.year, "month": date.month, "day": date.day}},
                "end": {"date": {"year": next_day.year, "month": next_day.month, "day": next_day.day}},
            }
        }
        try:
            resp = self._session.post(url, headers=self._auth_header(), json=body)
            resp.raise_for_status()
            data = resp.json()
            log.debug("%s rollup %s → %d points", data_type, date, len(data.get("rollupDataPoints", [])))
            return data
        except requests.HTTPError as e:
            log.warning("%s rollup %s → HTTP %s", data_type, date, e.response.status_code)
            return None
        except Exception as e:
            log.warning("%s rollup %s → %s", data_type, date, e)
            return None

    def _get_hr_for_window(self, start_utc: str, end_utc: str) -> dict[str, Any] | None:
        """Fetch all heart rate samples within [start_utc, end_utc), paginated."""
        url = f"{GOOGLE_HEALTH_BASE_URL}/users/me/dataTypes/heart-rate/dataPoints"
        filter_str = (
            f'heart_rate.sample_time.physical_time >= "{start_utc}"'
            f' AND heart_rate.sample_time.physical_time < "{end_utc}"'
        )
        params: dict[str, Any] = {"filter": filter_str, "pageSize": 1000}
        all_pts: list[dict] = []
        try:
            while True:
                resp = self._session.get(url, headers=self._auth_header(), params=params)
                resp.raise_for_status()
                data = resp.json()
                all_pts.extend(data.get("dataPoints", []))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                params = {"pageToken": page_token}
        except Exception as e:
            # Pagination may hit transient 500s; return whatever we have so far.
            if all_pts:
                log.debug("heart-rate pagination stopped early (%s) — using %d samples", e, len(all_pts))
            else:
                log.warning("heart-rate window fetch failed: %s", e)
                return None
        log.debug("heart-rate window %s–%s → %d samples", start_utc, end_utc, len(all_pts))
        return {"dataPoints": all_pts}

    @staticmethod
    def _sleep_window_for_date(sleep_payload: dict | None, date: datetime.date) -> tuple[str, str] | None:
        """Find the UTC start/end of the sleep session that ended on `date` (local time)."""
        if not sleep_payload:
            return None
        for pt in sleep_payload.get("dataPoints", []):
            try:
                interval = pt["sleep"]["interval"]
                end_utc = interval["endTime"]
                offset_s = int(interval["endUtcOffset"].rstrip("s"))
                end_dt = datetime.datetime.fromisoformat(end_utc.replace("Z", "+00:00"))
                local_end = (end_dt + datetime.timedelta(seconds=offset_s)).date()
                if local_end == date:
                    return interval["startTime"], interval["endTime"]
            except (KeyError, ValueError):
                continue
        return None

    # ------------------------------------------------------------------
    # Public fetchers
    # ------------------------------------------------------------------

    def get_sleep(self) -> dict[str, Any] | None:
        return self._get("sleep")

    def get_hrv(self) -> dict[str, Any] | None:
        return self._get("daily-heart-rate-variability")

    def get_spo2(self) -> dict[str, Any] | None:
        return self._get("daily-oxygen-saturation")

    def get_respiratory_rate(self) -> dict[str, Any] | None:
        return self._get("daily-respiratory-rate")

    def get_skin_temp(self) -> dict[str, Any] | None:
        return self._get("daily-sleep-temperature-derivations")

    def get_steps(self, date: datetime.date) -> dict[str, Any] | None:
        return self._post_daily_rollup("steps", date)

    def get_resting_hr(self) -> dict[str, Any] | None:
        return self._get("daily-resting-heart-rate")

    def get_weight(self) -> dict[str, Any] | None:
        return self._get("weight")

    def get_all(self, date: datetime.date) -> dict[str, Any]:
        sleep = self.get_sleep()

        heart_rate = None
        window = self._sleep_window_for_date(sleep, date)
        if window:
            heart_rate = self._get_hr_for_window(*window)

        return {
            "sleep": sleep,
            "hrv": self.get_hrv(),
            "spo2": self.get_spo2(),
            "respiratory_rate": self.get_respiratory_rate(),
            "skin_temp": self.get_skin_temp(),
            "steps": self.get_steps(date),
            "resting_hr": self.get_resting_hr(),
            "heart_rate": heart_rate,
            "weight": self.get_weight(),
        }
