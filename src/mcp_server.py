"""
MCP server exposing Fitbit-owned wellness fields from intervals.icu.

Reads from intervals.icu (where the sync lands data), never from Google Health
directly — that keeps this server stateless and free of OAuth concerns.

Tools:
  get_fitbit_wellness(date)     - full wellness row for one date
  get_fitbit_sleep(date)        - sleep subset for one date
  get_fitbit_readiness(days)    - composite over HRV, RHR, sleep across N days
"""

from __future__ import annotations

import datetime
import statistics
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.config import FITBIT_OWNED_FIELDS
from src.intervals_client import IntervalsClient

mcp = FastMCP("fitbit-air")

_client: IntervalsClient | None = None


def _get_client() -> IntervalsClient:
    global _client
    if _client is None:
        _client = IntervalsClient()
    return _client


def _parse_date(date: str) -> datetime.date:
    return datetime.date.fromisoformat(date)


def _fitbit_subset(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in FITBIT_OWNED_FIELDS if row.get(k) is not None}


@mcp.tool()
def get_fitbit_wellness(date: str) -> dict[str, Any]:
    """Return Fitbit-owned wellness fields stored in intervals.icu for `date` (YYYY-MM-DD).

    Only fields this sync owns are returned; Garmin-owned fields (activities, vo2max,
    training load, stress) are filtered out even if present.
    """
    row = _get_client().get_wellness(_parse_date(date))
    return {"date": date, **_fitbit_subset(row)}


@mcp.tool()
def get_fitbit_sleep(date: str) -> dict[str, Any]:
    """Return sleep-only fields for `date` (YYYY-MM-DD): sleepSecs, sleepScore,
    sleepQuality, avgSleepingHR."""
    row = _get_client().get_wellness(_parse_date(date))
    keys = ("sleepSecs", "sleepScore", "sleepQuality", "avgSleepingHR")
    return {"date": date, **{k: row.get(k) for k in keys if row.get(k) is not None}}


@mcp.tool()
def get_fitbit_readiness(days: int = 7) -> dict[str, Any]:
    """Composite readiness over the trailing N days (default 7).

    Returns per-day rows plus a summary with mean HRV, mean restingHR, mean sleepSecs,
    and a 0–100 composite score that weights HRV (40%), restingHR (30%), sleepScore (30%)
    against the trailing window's own baseline.
    """
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    rows = _get_client().get_wellness_range(start, end)

    series = [
        {"date": r.get("id"), **_fitbit_subset(r)}
        for r in rows
        if r.get("id")
    ]

    def _vals(key: str) -> list[float]:
        return [float(r[key]) for r in series if r.get(key) is not None]

    hrv_vals = _vals("hrv")
    rhr_vals = _vals("restingHR")
    sleep_score_vals = _vals("sleepScore")
    sleep_secs_vals = _vals("sleepSecs")

    summary: dict[str, Any] = {
        "window_days": days,
        "start": str(start),
        "end": str(end),
        "samples": len(series),
        "mean_hrv": round(statistics.mean(hrv_vals), 1) if hrv_vals else None,
        "mean_restingHR": round(statistics.mean(rhr_vals), 1) if rhr_vals else None,
        "mean_sleepSecs": int(statistics.mean(sleep_secs_vals)) if sleep_secs_vals else None,
        "mean_sleepScore": round(statistics.mean(sleep_score_vals), 1) if sleep_score_vals else None,
    }

    latest = series[-1] if series else {}
    summary["latest_composite"] = _composite(latest, hrv_vals, rhr_vals, sleep_score_vals)

    return {"summary": summary, "series": series}


def _composite(
    latest: dict[str, Any],
    hrv_window: list[float],
    rhr_window: list[float],
    sleep_score_window: list[float],
) -> float | None:
    """0–100 score: HRV vs window max (40%), RHR vs window min inverse (30%),
    sleepScore /100 (30%). Drops missing components and renormalizes weights."""
    parts: list[tuple[float, float]] = []

    hrv = latest.get("hrv")
    if hrv is not None and hrv_window:
        peak = max(hrv_window)
        if peak > 0:
            parts.append((min(float(hrv) / peak, 1.0) * 100, 0.4))

    rhr = latest.get("restingHR")
    if rhr is not None and rhr_window:
        floor = min(rhr_window)
        if rhr > 0:
            parts.append((min(floor / float(rhr), 1.0) * 100, 0.3))

    ss = latest.get("sleepScore")
    if ss is not None:
        parts.append((min(float(ss), 100.0), 0.3))

    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return round(sum(v * w for v, w in parts) / total_w, 1)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
