import datetime
from unittest.mock import MagicMock

import pytest

from src import mcp_server


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(mcp_server, "_client", client)
    return client


def _row(date: str, **fields):
    return {"id": date, **fields}


def _call(tool, **kwargs):
    return tool.fn(**kwargs) if hasattr(tool, "fn") else tool(**kwargs)


def test_get_fitbit_wellness_filters_garmin_fields(fake_client):
    fake_client.get_wellness.return_value = _row(
        "2026-05-28",
        restingHR=47,
        hrv=66.0,
        sleepSecs=8939,
        vo2max=57.0,
        ctl=22.6,
        atl=29.9,
        stress=None,
    )

    out = _call(mcp_server.get_fitbit_wellness, date="2026-05-28")

    assert out["date"] == "2026-05-28"
    assert out["restingHR"] == 47
    assert out["hrv"] == 66.0
    assert out["sleepSecs"] == 8939
    assert "vo2max" not in out
    assert "ctl" not in out
    assert "stress" not in out
    fake_client.get_wellness.assert_called_once_with(datetime.date(2026, 5, 28))


def test_get_fitbit_sleep_returns_only_sleep_fields(fake_client):
    fake_client.get_wellness.return_value = _row(
        "2026-05-28",
        sleepSecs=8939,
        sleepScore=82.0,
        sleepQuality=3,
        restingHR=47,
    )

    out = _call(mcp_server.get_fitbit_sleep, date="2026-05-28")

    assert out == {
        "date": "2026-05-28",
        "sleepSecs": 8939,
        "sleepScore": 82.0,
        "sleepQuality": 3,
    }


def test_readiness_composite_with_full_data(fake_client):
    fake_client.get_wellness_range.return_value = [
        _row("2026-05-26", hrv=60.0, restingHR=50, sleepScore=70.0, sleepSecs=27000),
        _row("2026-05-27", hrv=65.0, restingHR=48, sleepScore=80.0, sleepSecs=28800),
        _row("2026-05-28", hrv=70.0, restingHR=45, sleepScore=90.0, sleepSecs=30600),
    ]

    out = _call(mcp_server.get_fitbit_readiness, days=3)

    assert out["summary"]["samples"] == 3
    assert out["summary"]["mean_hrv"] == 65.0
    assert out["summary"]["mean_restingHR"] == 47.7
    # HRV 70/70*40 + RHR 45/45*30 + sleepScore 90*0.3 = 97.
    assert out["summary"]["latest_composite"] == pytest.approx(97.0, abs=0.1)
    assert [r["date"] for r in out["series"]] == [
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
    ]


def test_readiness_handles_missing_fields(fake_client):
    fake_client.get_wellness_range.return_value = [
        _row("2026-05-27", hrv=60.0),  # no RHR, no sleep
        _row("2026-05-28", hrv=70.0),
    ]

    out = _call(mcp_server.get_fitbit_readiness, days=2)

    assert out["summary"]["mean_restingHR"] is None
    assert out["summary"]["mean_sleepScore"] is None
    # Only HRV component available — score is hrv/peak * 100.
    assert out["summary"]["latest_composite"] == 100.0


def test_readiness_empty_window(fake_client):
    fake_client.get_wellness_range.return_value = []

    out = _call(mcp_server.get_fitbit_readiness, days=7)

    assert out["summary"]["samples"] == 0
    assert out["summary"]["latest_composite"] is None
    assert out["series"] == []
