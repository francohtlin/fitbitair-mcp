"""Mapper unit tests — fixture-based, no network."""

import datetime
import json
from pathlib import Path

import pytest

from src.mapper import map_day

FIXTURES = Path(__file__).parent / "fixtures"
TARGET = datetime.date(2026, 5, 28)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture()
def full_payload() -> dict:
    return {
        "sleep": _load("sleep"),
        "hrv": _load("hrv"),
        "spo2": _load("spo2"),
        "respiratory_rate": _load("respiratory_rate"),
        "skin_temp": _load("skin_temp"),
        "steps": _load("steps"),
        "resting_hr": _load("resting_hr"),
        "heart_rate": _load("heart_rate"),
        "weight": _load("weight"),
    }


# ---------------------------------------------------------------------------
# Field presence
# ---------------------------------------------------------------------------

def test_map_day_returns_expected_fields(full_payload: dict) -> None:
    result = map_day(full_payload, TARGET)
    assert "sleepSecs" in result
    assert "avgSleepingHR" in result
    assert "hrv" in result
    assert "spo2" in result
    assert "respiration" in result
    assert "skinTemp" in result
    assert "steps" in result
    assert "restingHR" in result
    assert "weight" in result


# ---------------------------------------------------------------------------
# Field values
# ---------------------------------------------------------------------------

def test_sleep_secs(full_payload: dict) -> None:
    result = map_day(full_payload, TARGET)
    # minutesAsleep = 513 → 513 * 60 = 30780
    assert result["sleepSecs"] == 30780


def test_avg_sleeping_hr(full_payload: dict) -> None:
    # Heart rate fixture has 3 samples inside the sleep window (03:14–11:47 UTC)
    # and 1 outside (20:00 UTC). Samples inside: 54, 58, 52 → avg 54.7
    result = map_day(full_payload, TARGET)
    assert result["avgSleepingHR"] == 54.7


def test_hrv(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["hrv"] == 42.7


def test_spo2(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["spo2"] == 95.5


def test_respiration(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["respiration"] == 14.8


def test_skin_temp(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["skinTemp"] == 0.38


def test_steps(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["steps"] == 9241


def test_resting_hr(full_payload: dict) -> None:
    assert map_day(full_payload, TARGET)["restingHR"] == 53


def test_weight_grams_to_kg(full_payload: dict) -> None:
    # weightGrams = 76400 → 76.4 kg
    assert map_day(full_payload, TARGET)["weight"] == 76.4


# ---------------------------------------------------------------------------
# Date filtering: wrong-date data is ignored
# ---------------------------------------------------------------------------

def test_hrv_wrong_date_ignored(full_payload: dict) -> None:
    wrong_date = datetime.date(2026, 5, 27)
    result = map_day(full_payload, wrong_date)
    assert "hrv" not in result


def test_sleep_wrong_date_ignored(full_payload: dict) -> None:
    wrong_date = datetime.date(2026, 5, 27)
    result = map_day(full_payload, wrong_date)
    assert "sleepSecs" not in result


# ---------------------------------------------------------------------------
# Safety contract: no nulls, no Garmin fields
# ---------------------------------------------------------------------------

def test_no_null_values(full_payload: dict) -> None:
    for k, v in map_day(full_payload, TARGET).items():
        assert v is not None, f"Field {k!r} must not be None"


def test_no_garmin_fields(full_payload: dict) -> None:
    garmin = {"ctl", "atl", "tsb", "vo2max", "bodyBattery", "stress",
              "mood", "fatigue", "motivation", "activities",
              "sleepScore", "sleepQuality", "readiness"}
    overlap = garmin & map_day(full_payload, TARGET).keys()
    assert not overlap, f"Garmin/unavailable fields in output: {overlap}"


def test_all_none_returns_empty() -> None:
    payload = {k: None for k in ("sleep", "hrv", "spo2", "respiratory_rate",
                                  "skin_temp", "steps", "resting_hr",
                                  "heart_rate", "weight")}
    assert map_day(payload, TARGET) == {}


def test_zero_steps_omitted() -> None:
    payload = {
        "steps": {"rollupDataPoints": [{"steps": {"countSum": "0"}}]},
        **{k: None for k in ("sleep", "hrv", "spo2", "respiratory_rate",
                              "skin_temp", "resting_hr", "heart_rate", "weight")},
    }
    assert "steps" not in map_day(payload, TARGET)


def test_skin_temp_nan_omitted() -> None:
    payload = {
        "skin_temp": {"dataPoints": [{
            "dailySleepTemperatureDerivations": {
                "date": {"year": 2026, "month": 5, "day": 28},
                "nightlyTemperatureCelsius": 32.876,
                "baselineTemperatureCelsius": "NaN",
                "relativeNightlyStddev30dCelsius": "NaN",
            }
        }]},
        **{k: None for k in ("sleep", "hrv", "spo2", "respiratory_rate",
                              "steps", "resting_hr", "heart_rate", "weight")},
    }
    assert "skinTemp" not in map_day(payload, TARGET)
