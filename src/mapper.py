"""
Pure function: Google Health API day payload → intervals.icu wellness dict.

Verified field paths from Sprint 0 (2026-05-28):

  sleep.summary.minutesAsleep (str)           → sleepSecs
  dailyHeartRateVariability
    .averageHeartRateVariabilityMilliseconds   → hrv
  dailyRestingHeartRate.beatsPerMinute (str)  → restingHR
  dailyOxygenSaturation.averagePercentage     → spo2
  dailyRespiratoryRate.breathsPerMinute       → respiration
  dailySleepTemperatureDerivations
    .relativeNightlyStddev30dCelsius          → skinTemp (NaN when <30d baseline)
  rollupDataPoints[0].steps.countSum (str)    → steps   (from :dailyRollUp POST)
  weight.weightGrams (int)                    → weight  (÷ 1000 → kg)
  heart-rate samples during sleep window      → avgSleepingHR

Not in the API (dropped):
  sleepScore, sleepQuality — not exposed
  readiness — not exposed
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _matches_date(date_obj: dict, target: datetime.date) -> bool:
    return (
        date_obj.get("year") == target.year
        and date_obj.get("month") == target.month
        and date_obj.get("day") == target.day
    )


def _civil_end_date(pt: dict, key: str) -> datetime.date | None:
    """Extract the civil end date from a sleep data point."""
    try:
        end = pt[key]["interval"]["endTime"]  # e.g. "2026-05-28T12:50:00Z"
        offset_s = int(pt[key]["interval"]["endUtcOffset"].rstrip("s"))
        utc_dt = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))
        local_dt = utc_dt + datetime.timedelta(seconds=offset_s)
        return local_dt.date()
    except Exception:
        return None


def _parse_utc(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Per-type extractors
# ---------------------------------------------------------------------------

def _extract_sleep(
    sleep_payload: dict | None,
    heart_rate_payload: dict | None,
    target: datetime.date,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not sleep_payload:
        return out

    # Find the sleep session that ended on target date (local time)
    pt = None
    for p in sleep_payload.get("dataPoints", []):
        if _civil_end_date(p, "sleep") == target:
            pt = p
            break
    if not pt:
        return out

    sleep = pt["sleep"]
    summary = sleep.get("summary", {})

    minutes_asleep = summary.get("minutesAsleep")
    if minutes_asleep:
        secs = int(minutes_asleep) * 60
        if secs > 0:
            out["sleepSecs"] = secs

    # avgSleepingHR: average heart rate samples within the sleep window
    avg_hr = _avg_sleeping_hr(sleep, heart_rate_payload)
    if avg_hr:
        out["avgSleepingHR"] = avg_hr

    return out


def _avg_sleeping_hr(
    sleep: dict,
    heart_rate_payload: dict | None,
) -> float | None:
    if not heart_rate_payload:
        return None
    try:
        interval = sleep["interval"]
        sleep_start = _parse_utc(interval["startTime"])
        sleep_end = _parse_utc(interval["endTime"])
    except (KeyError, ValueError):
        return None

    readings = []
    for pt in heart_rate_payload.get("dataPoints", []):
        try:
            sample_time = _parse_utc(pt["heartRate"]["sampleTime"]["physicalTime"])
            if sleep_start <= sample_time <= sleep_end:
                readings.append(int(pt["heartRate"]["beatsPerMinute"]))
        except (KeyError, ValueError):
            continue

    if not readings:
        return None
    return round(sum(readings) / len(readings), 1)


def _extract_hrv(hrv_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (hrv_payload or {}).get("dataPoints", []):
        d = pt.get("dailyHeartRateVariability", {})
        if not _matches_date(d.get("date", {}), target):
            continue
        rmssd = d.get("averageHeartRateVariabilityMilliseconds")
        if rmssd and float(rmssd) > 0:
            return {"hrv": round(float(rmssd), 1)}
    return {}


def _extract_spo2(spo2_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (spo2_payload or {}).get("dataPoints", []):
        d = pt.get("dailyOxygenSaturation", {})
        if not _matches_date(d.get("date", {}), target):
            continue
        pct = d.get("averagePercentage")
        if pct and float(pct) > 0:
            return {"spo2": round(float(pct), 1)}
    return {}


def _extract_respiratory_rate(resp_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (resp_payload or {}).get("dataPoints", []):
        d = pt.get("dailyRespiratoryRate", {})
        if not _matches_date(d.get("date", {}), target):
            continue
        bpm = d.get("breathsPerMinute")
        if bpm and float(bpm) > 0:
            return {"respiration": round(float(bpm), 1)}
    return {}


def _extract_skin_temp(temp_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (temp_payload or {}).get("dataPoints", []):
        d = pt.get("dailySleepTemperatureDerivations", {})
        if not _matches_date(d.get("date", {}), target):
            continue
        # relativeNightlyStddev30dCelsius requires 30-day baseline; may be "NaN"
        raw = d.get("relativeNightlyStddev30dCelsius")
        if raw is None:
            continue
        try:
            val = float(raw)
            if not math.isnan(val):
                return {"skinTemp": round(val, 2)}
        except (ValueError, TypeError):
            pass
    return {}


def _extract_steps(steps_payload: dict | None) -> dict[str, Any]:
    # steps uses :dailyRollUp — response key is rollupDataPoints
    for pt in (steps_payload or {}).get("rollupDataPoints", []):
        count = pt.get("steps", {}).get("countSum")
        if count and int(count) > 0:
            return {"steps": int(count)}
    return {}


def _extract_resting_hr(rhr_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (rhr_payload or {}).get("dataPoints", []):
        d = pt.get("dailyRestingHeartRate", {})
        if not _matches_date(d.get("date", {}), target):
            continue
        bpm = d.get("beatsPerMinute")
        if bpm and int(bpm) > 0:
            return {"restingHR": int(bpm)}
    return {}


def _extract_weight(weight_payload: dict | None, target: datetime.date) -> dict[str, Any]:
    for pt in (weight_payload or {}).get("dataPoints", []):
        w = pt.get("weight", {})
        civil = w.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if not _matches_date(civil, target):
            continue
        grams = w.get("weightGrams")
        if grams and int(grams) > 0:
            return {"weight": round(int(grams) / 1000, 2)}
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_day(fitbit_day_payload: dict[str, Any], target: datetime.date) -> dict[str, Any]:
    """
    Map one day of Google Health API responses to an intervals.icu wellness dict.

    Input keys: sleep, hrv, spo2, respiratory_rate, skin_temp, steps,
                resting_hr, heart_rate, weight
    target: the civil date the data belongs to

    Output: dict with only Fitbit-owned fields that have real values (no nulls).
    """
    out: dict[str, Any] = {}

    out.update(_extract_sleep(
        fitbit_day_payload.get("sleep"),
        fitbit_day_payload.get("heart_rate"),
        target,
    ))
    out.update(_extract_hrv(fitbit_day_payload.get("hrv"), target))
    out.update(_extract_spo2(fitbit_day_payload.get("spo2"), target))
    out.update(_extract_respiratory_rate(fitbit_day_payload.get("respiratory_rate"), target))
    out.update(_extract_skin_temp(fitbit_day_payload.get("skin_temp"), target))
    out.update(_extract_steps(fitbit_day_payload.get("steps")))
    out.update(_extract_resting_hr(fitbit_day_payload.get("resting_hr"), target))
    out.update(_extract_weight(fitbit_day_payload.get("weight"), target))

    log.debug("Mapped fields for %s: %s", target, list(out.keys()))
    return out
