# fitbitair-mcp

Fitbit Air → intervals.icu sync service. Pulls wellness data from the Google Health API and writes Fitbit-owned fields to intervals.icu daily.

## Morning pull

When the user says **"morning pull"** (or "morning", "pull today's data", "sync today"):

1. Run the Fitbit sync for today:
   ```bash
   cd /Users/francohtlin1/fitbitair-mcp && uv run fitbit-sync
   ```
2. Call **all three** MCPs in parallel:
   - `mcp__fitbit__get_fitbit_wellness` with today's date (YYYY-MM-DD)
   - `mcp__fitbit__get_fitbit_activities` with yesterday's date (YYYY-MM-DD)
   - `mcp__garmin__get_wellness` with `days=1`
3. Present a morning summary with two clearly labelled sections:

**⌚ Fitbit Air** (from `get_fitbit_wellness` + `get_fitbit_activities`):
- Sleep: sleepSecs → convert to h:mm format, avgSleepingHR
- Recovery: hrv, restingHR, spO2, respiration, skinTemp (omit if null)
- Body: weight, steps
- Workouts (from `get_fitbit_activities` for yesterday): list sessions if any (type, duration, calories)

**🏃 Garmin** (from `get_wellness`):
- Training load: ctl, atl, ramp_rate
- Recovery: body_battery, stress (if present)
- Performance: vo2max (if present)
- Any activities from that day

If the Fitbit sync fails, report the error clearly and still show the Garmin data.
If a field is null/missing from either source, omit it silently — don't show null rows.

## Day pull

When the user says **"day pull"**, **"fitbit check"**, **"how's my body today"**, or **"fitbit only"**:

1. Sync today's latest data from the Air:
   ```bash
   cd /Users/francohtlin1/fitbitair-mcp && uv run fitbit-sync --date <today>
   ```
2. Call **both** in parallel:
   - `fitbit:get_fitbit_wellness` with today's date
   - `fitbit:get_fitbit_activities` with today's date
3. Present a **Fitbit Air only** summary — no Garmin fields, no training load:

**⌚ Fitbit Air — [date]**
- Sleep: sleepSecs → h:mm, avgSleepingHR (last night)
- Body: restingHR, hrv (RMSSD), spO2, respiration (omit if null)
- Activity: steps so far today, weight (if logged)
- Workouts: list any exercise sessions (type, duration, calories) — omit section if none
- skinTemp variation (only if available — needs 30-day baseline)

Omit any field that is null. Do not show Garmin fields (ctl, atl, stress, etc.).
This pull is intentionally Fitbit-only — the user wears the Fitbit Air all day and
the Garmin only for workouts, so these are the all-day biometrics.

## Field ownership

This service writes only: sleepSecs, avgSleepingHR, hrv, restingHR, spO2, respiration, skinTemp, steps, weight

Never overwrite: ctl, atl, tsb, vo2max, bodyBattery, stress, mood, fatigue, motivation, activities

## CLI

```bash
uv run fitbit-sync                    # sync yesterday
uv run fitbit-sync --date 2026-05-28  # specific date
uv run fitbit-sync --days 7           # last 7 days
uv run fitbit-sync --dry-run          # preview without writing
uv run fitbit-sync --today            # sync today (daytime pull)
```

## Project layout

```
src/fitbit_client.py    Google Health API wrapper
src/mapper.py           API response → intervals.icu field mapping
src/intervals_client.py intervals.icu REST wrapper
src/auth.py             Google OAuth 2.0 token management
src/sync.py             CLI entrypoint
src/mcp_server.py       MCP tools (get_fitbit_wellness, get_fitbit_sleep, get_fitbit_readiness, get_fitbit_activities)
```
