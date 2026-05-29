"""
Run once to complete the Google OAuth dance and persist tokens.

Prerequisites:
  1. Register a Google Cloud project at console.cloud.google.com
  2. Enable the Google Health API
  3. Create OAuth 2.0 credentials (Desktop app type)
  4. Either:
     a. Download client_secrets.json to ~/.config/fitbit-intervals-sync/client_secrets.json
     b. Or set FITBIT_CLIENT_ID + FITBIT_CLIENT_SECRET in .env

Usage (from repo root):
  uv run python scripts/one_time_auth.py
"""

import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import run_initial_auth
from src.config import TOKEN_PATH


def main() -> None:
    print("Starting Google Health API OAuth flow...")
    print("A browser window will open. Log in and grant the requested permissions.")
    print()

    creds = run_initial_auth()
    print(f"\nSuccess! Tokens saved to {TOKEN_PATH}")
    print(f"Access token expires: {creds.expiry}")
    print("\nYou can now run: fitbit-sync --dry-run --date <yesterday>")


if __name__ == "__main__":
    main()
