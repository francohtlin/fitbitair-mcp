"""
OAuth 2.0 for the Google Health API.

App registration: Google Cloud Console → APIs & Services → Credentials
→ Create OAuth 2.0 Client ID → Desktop app.
Download client_secrets.json to ~/.config/fitbit-intervals-sync/client_secrets.json,
OR set FITBIT_CLIENT_ID + FITBIT_CLIENT_SECRET in .env.

Initial flow: run scripts/one_time_auth.py once.
Subsequent calls: get_credentials() auto-refreshes when expiry is within 60 s.
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import google.auth.transport.requests
import google.oauth2.credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import (
    CLIENT_SECRETS_PATH,
    FITBIT_CLIENT_ID,
    FITBIT_CLIENT_SECRET,
    MIN_TOKEN_LIFETIME_SECONDS,
    OAUTH_REDIRECT_PORT,
    OAUTH_SCOPES,
    TOKEN_PATH,
)


def _client_config() -> dict:
    if CLIENT_SECRETS_PATH.exists():
        return json.loads(CLIENT_SECRETS_PATH.read_text())
    if FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET:
        return {
            "installed": {
                "client_id": FITBIT_CLIENT_ID,
                "client_secret": FITBIT_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"http://127.0.0.1:{OAUTH_REDIRECT_PORT}/callback"],
            }
        }
    raise RuntimeError(
        f"No OAuth credentials found.\n"
        f"Either place client_secrets.json at {CLIENT_SECRETS_PATH}\n"
        f"or set FITBIT_CLIENT_ID + FITBIT_CLIENT_SECRET in .env"
    )


def _save_tokens(creds: google.oauth2.credentials.Credentials) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else OAUTH_SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    TOKEN_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _load_tokens() -> google.oauth2.credentials.Credentials | None:
    if not TOKEN_PATH.exists():
        return None
    data = json.loads(TOKEN_PATH.read_text())
    expiry = datetime.fromisoformat(data["expiry"]) if data.get("expiry") else None
    return google.oauth2.credentials.Credentials(
        token=data["token"],
        refresh_token=data.get("refresh_token"),
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
        expiry=expiry,
    )


def get_credentials() -> google.oauth2.credentials.Credentials:
    creds = _load_tokens()
    if creds is None:
        raise RuntimeError(
            f"No tokens at {TOKEN_PATH}. Run: python scripts/one_time_auth.py"
        )

    if creds.expiry:
        expiry = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry.tzinfo is None else creds.expiry
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        if remaining < MIN_TOKEN_LIFETIME_SECONDS:
            creds.refresh(google.auth.transport.requests.Request())
            _save_tokens(creds)

    return creds


def run_initial_auth(port: int = OAUTH_REDIRECT_PORT) -> google.oauth2.credentials.Credentials:
    flow = InstalledAppFlow.from_client_config(_client_config(), scopes=OAUTH_SCOPES)
    creds = flow.run_local_server(port=port, prompt="consent")
    _save_tokens(creds)
    return creds
