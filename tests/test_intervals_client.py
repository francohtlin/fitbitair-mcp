"""intervals_client unit tests — no network (uses responses library)."""

import datetime

import pytest
import responses as resp_lib

from src.intervals_client import IntervalsClient

DATE = datetime.date(2026, 5, 27)
ATHLETE_ID = "test_athlete"
API_KEY = "test_key"
WELLNESS_URL = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness/{DATE}"

PAYLOAD = {
    "sleepSecs": 30780,
    "sleepScore": 76,
    "sleepQuality": 3,
    "restingHR": 53,
    "hrv": 42.7,
}


@pytest.fixture()
def client() -> IntervalsClient:
    return IntervalsClient(athlete_id=ATHLETE_ID, api_key=API_KEY)


def test_dry_run_skips_http(client: IntervalsClient) -> None:
    result = client.put_wellness(DATE, PAYLOAD, dry_run=True)
    assert result == PAYLOAD


@resp_lib.activate
def test_put_wellness_sends_correct_request(client: IntervalsClient) -> None:
    resp_lib.add(resp_lib.PUT, WELLNESS_URL, json=PAYLOAD, status=200)
    result = client.put_wellness(DATE, PAYLOAD)
    assert result == PAYLOAD

    import base64
    req = resp_lib.calls[0].request
    assert req.method == "PUT"
    auth_header = req.headers.get("Authorization", "")
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode()
    assert decoded == f"API_KEY:{API_KEY}"


@resp_lib.activate
def test_put_wellness_raises_on_http_error(client: IntervalsClient) -> None:
    resp_lib.add(resp_lib.PUT, WELLNESS_URL, status=401)
    with pytest.raises(Exception):
        client.put_wellness(DATE, PAYLOAD)


def test_missing_credentials_raises() -> None:
    with pytest.raises(RuntimeError, match="INTERVALS_ATHLETE_ID"):
        IntervalsClient(athlete_id="", api_key="")
