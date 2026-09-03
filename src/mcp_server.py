"""
MCP server exposing Fitbit-owned wellness fields from intervals.icu.

Reads from intervals.icu (where the sync lands data), never from Google Health
directly — that keeps this server stateless and free of OAuth concerns.

Tools:
  get_fitbit_wellness(date)     - full wellness row for one date
  get_fitbit_sleep(date)        - sleep subset for one date
  get_fitbit_readiness(days)    - composite over HRV, RHR, sleep across N days
  get_fitbit_activities(date)   - exercise sessions for one date (direct from Google Health API)
"""

from __future__ import annotations

import datetime
import statistics
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.config import FITBIT_OWNED_FIELDS
from src.fitbit_client import GoogleHealthClient
from src.intervals_client import IntervalsClient

mcp = FastMCP("fitbit-air")

_client: IntervalsClient | None = None
_fitbit_client: GoogleHealthClient | None = None


def _get_fitbit_client() -> GoogleHealthClient:
    global _fitbit_client
    if _fitbit_client is None:
        _fitbit_client = GoogleHealthClient()
    return _fitbit_client


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


@mcp.tool()
def get_fitbit_activities(date: str) -> dict[str, Any]:
    """Return exercise sessions tracked by Fitbit Air for `date` (YYYY-MM-DD).

    Fetches directly from Google Health API (not intervals.icu). Returns each
    session with activity type, duration, start/end times, calories, steps,
    distance, average HR, and heart rate zone breakdown. Only Fitbit-platform
    sessions are returned — Health Connect / phone auto-detects are excluded.
    """
    target = _parse_date(date)
    raw = _get_fitbit_client().get_exercise_sessions(target)

    if not raw or not raw.get("dataPoints"):
        return {"date": date, "count": 0, "sessions": []}

    sessions: list[dict[str, Any]] = []
    for pt in raw["dataPoints"]:
        ex = pt.get("exercise", {})
        interval = ex.get("interval", {})
        metrics = ex.get("metricsSummary", {})

        entry: dict[str, Any] = {}

        name = ex.get("displayName") or ex.get("exerciseType")
        if name:
            entry["type"] = name

        start_str = interval.get("startTime")
        end_str = interval.get("endTime")
        if start_str:
            entry["start"] = start_str
        if end_str:
            entry["end"] = end_str

        active_dur = ex.get("activeDuration", "")
        if active_dur:
            try:
                secs = float(active_dur.rstrip("s"))
                entry["duration_mins"] = round(secs / 60, 1)
            except ValueError:
                pass

        cal = metrics.get("caloriesKcal")
        if cal is not None:
            entry["calories_kcal"] = int(cal)

        dist_mm = metrics.get("distanceMillimeters")
        if dist_mm:
            entry["distance_km"] = round(int(dist_mm) / 1_000_000, 2)

        steps = metrics.get("steps")
        if steps:
            entry["steps"] = int(steps)

        avg_hr = metrics.get("averageHeartRateBeatsPerMinute")
        if avg_hr:
            entry["avg_hr"] = int(avg_hr)

        azm = metrics.get("activeZoneMinutes")
        if azm:
            entry["active_zone_mins"] = int(azm)

        zones = metrics.get("heartRateZoneDurations", {})
        if zones:
            def _mins(val: str) -> int:
                return int(int(val.rstrip("s")) / 60) if val else 0
            entry["hr_zones"] = {
                "light": _mins(zones.get("lightTime", "0s")),
                "moderate": _mins(zones.get("moderateTime", "0s")),
                "vigorous": _mins(zones.get("vigorousTime", "0s")),
                "peak": _mins(zones.get("peakTime", "0s")),
            }

        sessions.append(entry)

    return {"date": date, "count": len(sessions), "sessions": sessions}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
