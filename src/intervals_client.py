"""
intervals.icu wellness API wrapper.

PUT /api/v1/athlete/{id}/wellness/{date}
  Auth: Basic API_KEY:{api_key}
  Body: JSON dict of wellness fields

The PUT is destructive per-key: any key present overwrites, any key absent
is preserved. Never send None or zero sentinels.
"""

import datetime
import logging
from typing import Any

import requests

from src.config import INTERVALS_API_KEY, INTERVALS_ATHLETE_ID, INTERVALS_BASE_URL

log = logging.getLogger(__name__)


class IntervalsClient:
    def __init__(
        self,
        athlete_id: str = INTERVALS_ATHLETE_ID,
        api_key: str = INTERVALS_API_KEY,
    ) -> None:
        if not athlete_id or not api_key:
            raise RuntimeError(
                "INTERVALS_ATHLETE_ID and INTERVALS_API_KEY must be set in .env"
            )
        self._athlete_id = athlete_id
        self._session = requests.Session()
        self._session.auth = ("API_KEY", api_key)

    def put_wellness(
        self,
        date: datetime.date,
        payload: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        url = f"{INTERVALS_BASE_URL}/api/v1/athlete/{self._athlete_id}/wellness/{date}"
        log.info("PUT %s fields=%s dry_run=%s", date, list(payload.keys()), dry_run)

        if dry_run:
            log.info("DRY RUN payload: %s", payload)
            return payload

        resp = self._session.put(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_wellness(self, date: datetime.date) -> dict[str, Any]:
        url = f"{INTERVALS_BASE_URL}/api/v1/athlete/{self._athlete_id}/wellness/{date}"
        resp = self._session.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_wellness_range(
        self, start: datetime.date, end: datetime.date
    ) -> list[dict[str, Any]]:
        url = f"{INTERVALS_BASE_URL}/api/v1/athlete/{self._athlete_id}/wellness"
        resp = self._session.get(url, params={"oldest": str(start), "newest": str(end)})
        resp.raise_for_status()
        return resp.json()
