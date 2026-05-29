import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GOOGLE_HEALTH_BASE_URL = "https://health.googleapis.com/v4"
INTERVALS_BASE_URL = "https://intervals.icu"

CONFIG_DIR = Path.home() / ".config" / "fitbit-intervals-sync"
TOKEN_PATH = CONFIG_DIR / "tokens.json"
CLIENT_SECRETS_PATH = CONFIG_DIR / "client_secrets.json"

MIN_TOKEN_LIFETIME_SECONDS = 60

SYNC_TIMEZONE = os.getenv("SYNC_TIMEZONE", "America/Toronto")

INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "")
INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY", "")

FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID", "")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET", "")

# Fields this service owns. Never PUT a field not on this list.
FITBIT_OWNED_FIELDS = [
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
    "restingHR",
    "hrv",
    "avgSleepingHR",
    "spO2",
    "respiration",
    "skinTemp",
    "steps",
    "weight",
    "readiness",
]

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]

OAUTH_REDIRECT_PORT = 8080
