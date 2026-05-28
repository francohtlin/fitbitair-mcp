# Fitbit Air → intervals.icu Sync

A daily wellness sync that pushes Fitbit Air data into intervals.icu without overwriting fields owned by the Garmin Vivoactive 5 pipeline.

## Context

Two wearables, stacked:
- **Fitbit Air** — worn ~22h/day (work, sleep, around the house). Owns all-day and overnight wellness.
- **Garmin Vivoactive 5** — worn for workouts only. Owns activities, training load, workout-time metrics.

Garmin already writes to intervals.icu via Garmin Connect → intervals.icu (existing path, do not touch). This service writes Fitbit-owned wellness fields. Conflicts are avoided through **field partitioning**, not locking: each wellness field has exactly one owner, and the non-owner never writes it.

## Architecture

```
Fitbit Air ──► Fitbit cloud / Google Health API
                            │
                            ▼
                    sync_service (this repo)
                            │
                            ▼
            intervals.icu PUT /api/v1/athlete/{id}/wellness/{date}
                            ▲
                            │
Garmin Vivoactive 5 ──► Garmin Connect ──┘ (existing path, untouched)
```

## Data ownership matrix

The contract. Sprint 0 confirms availability on the Air; the writer only sends Fitbit-owned fields that Sprint 0 confirmed are exposed.

| intervals.icu field | Owner | Fitbit source |
|---|---|---|
| `sleepSecs` | Fitbit | sleep endpoint → totalMinutesAsleep × 60 |
| `sleepScore` | Fitbit | sleep endpoint score (0–100) |
| `sleepQuality` | Fitbit | bucketed from sleepScore (1–4) |
| `restingHR` | Fitbit | heart rate summary |
| `hrv` | Fitbit | daily RMSSD |
| `avgSleepingHR` | Fitbit | heart rate during sleep stages |
| `spo2` | Fitbit | spo2 daily |
| `respiration` | Fitbit | breathing rate daily |
| `skinTemp` | Fitbit | temp/skin nightly variation |
| `steps` | Fitbit | activities/steps |
| `weight` | Fitbit | body/log/weight (only if Fitbit scale paired) |
| `readiness` | Fitbit | Fitbit Daily Readiness Score (verify Air exposes) |
| `activities` | Garmin | DO NOT push |
| `ctl` / `atl` / `tsb` | Garmin | computed by intervals from activities |
| `vo2max` | Garmin | DO NOT push |
| `bodyBattery` | Garmin | DO NOT push |
| `stress` | Garmin | DO NOT push |
| `mood` / `fatigue` / `motivation` | Manual | DO NOT push |

**Critical**: the intervals.icu PUT upserts. Any key sent overwrites. Any key absent is preserved. Sending `null` overwrites with null. The mapper must **omit** absent or zero-sentinel values, never null them.

## Repo structure

```
fitbit-intervals-sync/
├── README.md                # this file
├── pyproject.toml           # uv-managed
├── .env.example
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── fitbit_client.py     # Fitbit / Google Health API wrapper
│   ├── intervals_client.py  # intervals.icu wrapper
│   ├── auth.py              # OAuth 2.0 PKCE + token store
│   ├── mapper.py            # Fitbit JSON → intervals wellness dict
│   ├── sync.py              # orchestrator + CLI entrypoint
│   └── config.py            # field ownership constants, paths, base URLs
├── scripts/
│   ├── one_time_auth.py     # initial OAuth dance
│   └── backfill.py          # historical backfill
├── tests/
│   ├── test_mapper.py       # fixture-based, no network
│   ├── test_intervals_client.py
│   └── fixtures/            # sample API responses
├── notes/
│   └── sprint-0-findings.md # filled in during Sprint 0
└── deploy/
    └── com.franco.fitbit-sync.plist  # macOS launchd agent
```

## Sprint 0: API verification (no code)

**The most important step.** The Fitbit Air launched May 26, 2026. The old Fitbit Web API is being subsumed by the new Google Health API. Forum chatter shows community confusion about which endpoints work for the Air. Confirm reality before writing a line of code.

Tasks:

1. Visit `dev.fitbit.com`. Confirm whether new app registration is still supported there, or if it redirects to `developers.google.com/health`.
2. Register a developer app on whichever is current. Capture client ID + secret. Set callback URL to `http://127.0.0.1:8080/callback`.
3. Manually OAuth into your own account via `curl` + browser.
4. For each Fitbit-owned field in the matrix, hit the corresponding endpoint with `curl` for yesterday's date.
5. Output `notes/sprint-0-findings.md` with each endpoint, current URL, sample response (or 404 / no data), and a verdict.

The Sprint 0 findings trim the matrix. Anything the Air doesn't expose gets dropped from Sprint 3.

## Sprint 1: scaffold + OAuth

- Scaffold the repo per the structure above. Python 3.12, `uv` for deps, `pyproject.toml`.
- `src/auth.py`: OAuth 2.0 with PKCE. Token store at `~/.config/fitbit-intervals-sync/tokens.json` (chmod 0600). Refresh logic: if `expires_at - now < 60s`, refresh before any API call and persist the new token pair.
- `scripts/one_time_auth.py`: spins up local HTTP server on 127.0.0.1:8080, opens browser to auth URL, captures the auth code on callback, exchanges for tokens, persists to disk.
- `src/fitbit_client.py`: just enough to fetch yesterday's sleep JSON and return it.

Acceptance: `python scripts/one_time_auth.py` completes end to end. `fitbit-sync --dry-run --date <yesterday>` prints sleep JSON to stdout.

## Sprint 2: mapper + first intervals.icu write

- `src/mapper.py`: pure function `(fitbit_day_payload) -> intervals_wellness_dict`. Sleep-only for this sprint. Unit tested against fixture JSON.
- `src/intervals_client.py`:

```
  PUT https://intervals.icu/api/v1/athlete/{athlete_id}/wellness/{yyyy-mm-dd}
  Authorization: Basic API_KEY:{api_key}
  Content-Type: application/json
  Body: { only Fitbit-owned fields, no nulls, no zero sentinels }
```

- Wire `src/sync.py` to call fitbit_client → mapper → intervals_client for one date.
- Run for yesterday. Open intervals.icu UI and verify sleep fields populated and Garmin-owned fields (stress, training load) untouched.

Acceptance: `sleepSecs`, `sleepScore`, `avgSleepingHR` visible for yesterday in intervals. Garmin-owned fields unchanged.

## Sprint 3: remaining fields

Extend mapper and orchestrator to cover every endpoint Sprint 0 confirmed:
- HRV daily (RMSSD)
- SpO2
- Respiratory rate
- Skin temp variation
- Steps
- Resting HR
- Weight (if scale paired)
- Readiness score (if Air exposes it)

Drop quietly any field Sprint 0 marked unavailable. Don't push zero or sentinel values.

Acceptance: a daily sync writes every confirmed Fitbit-owned field, omits unavailable ones, and a manual spot-check of yesterday's intervals row matches the Fitbit app within rounding.

## Sprint 4: scheduling + backfill

- `scripts/backfill.py --days 30`: idempotent backfill for the last N days. Re-runnable safely.
- `deploy/com.franco.fitbit-sync.plist`: launchd agent, runs daily at 05:00 local time. Logs to `~/Library/Logs/fitbit-sync.log`. If the laptop is asleep, launchd runs on next wake.
- Load: `launchctl load ~/Library/LaunchAgents/com.franco.fitbit-sync.plist`.

Acceptance: 30-day backfill visible in intervals.icu. Next morning, log shows yesterday's auto-sync ran successfully.

## Sprint 5 (optional, later): MCP wrapper

Only build this if conversational queries against Fitbit data become a real need. The existing garmin_mcp `get_wellness` tool already returns Fitbit-sourced fields once they land in intervals.icu, so for most analysis it's redundant.

If built, mirror the garmin_mcp pattern and expose:
- `get_fitbit_wellness(date)`
- `get_fitbit_sleep(date)`
- `get_fitbit_readiness(days)` — composite over HRV, RHR, sleep score

## CLI

```bash
fitbit-sync                          # sync yesterday
fitbit-sync --date 2026-05-27        # one specific day
fitbit-sync --days 7                 # last 7 days
fitbit-sync --from 2026-05-01 --to 2026-05-27   # range
fitbit-sync --dry-run                # log payloads, don't PUT
fitbit-sync --verbose
```

Idempotent. Re-running for the same date is safe.

## Conflict avoidance with Garmin

Three layers, in priority order:

1. **Field partitioning** (primary). The ownership matrix is the contract. Never PUT a field Garmin owns. This is the only thing that actually matters.
2. **Run order** (defensive). Schedule Fitbit sync at 05:00, after the typical Garmin Connect overnight sync. If a partitioning bug ever sneaks in, Fitbit's value wins for fields it should win.
3. **Logging** (observability). Every sync run logs the exact field set written. Grep logs by date when something looks off.

Do not assume intervals.icu has PATCH semantics or merge logic. Assume PUT is destructive on every key present in the payload.

## Configuration

`.env`:

```
FITBIT_CLIENT_ID=...
FITBIT_CLIENT_SECRET=...
INTERVALS_ATHLETE_ID=...
INTERVALS_API_KEY=...
SYNC_TIMEZONE=America/Toronto
```

`src/config.py` constants:
- `FITBIT_OWNED_FIELDS = [...]` (sourced from the matrix)
- `MIN_TOKEN_LIFETIME_SECONDS = 60`
- `INTERVALS_BASE_URL = "https://intervals.icu"`
- `FITBIT_BASE_URL` — set in Sprint 0 based on findings

## Out of scope (v1)

- Workout activity import. Garmin owns.
- Real-time push via subscriber/webhook API. Daily polling is sufficient.
- Web UI. CLI only.
- Multi-user. Single Fitbit account, single intervals.icu athlete.
- Bi-directional sync. intervals is the destination, full stop.

## Kickoff prompt for Claude Code

Paste this as the first message in a Claude Code session inside the repo:

> Read README.md. We're starting Sprint 0. Don't write any code yet. Verify whether the Fitbit Air still uses api.fitbit.com or has migrated to the new Google Health API at developers.google.com/health. For each endpoint in the ownership matrix, output its current URL and a curl command I can run to confirm the Air exposes data. Write the verification checklist to notes/sprint-0-findings.md and stop. I'll run the curls myself and report back.
