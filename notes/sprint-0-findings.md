# Sprint 0 Findings — API Verification

## Summary

The Fitbit Air launched 2026-05-26. The legacy Fitbit Web API (`api.fitbit.com`) is
being replaced by the Google Health API. New integrations should target the new API.

**Decision: use Google Health API (`health.googleapis.com/v4/`).**

The legacy API still works until September 2026, but new app registration now flows
through Google Cloud Console, and all data from the Air is available via the new API.

---

## App Registration

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Health API** (search "Google Health API" in API Library)
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download `client_secrets.json` → place at `~/.config/fitbit-intervals-sync/client_secrets.json`
   OR copy `client_id` and `client_secret` into `.env`

---

## OAuth Scopes

```
https://www.googleapis.com/auth/googlehealth.sleep.readonly
https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly
https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly
```

---

## Endpoint Verification

Base URL: `https://health.googleapis.com/v4`

Run these after completing OAuth (`scripts/one_time_auth.py`) to get `ACCESS_TOKEN`:

```bash
ACCESS_TOKEN=$(python -c "
from src.auth import get_credentials
print(get_credentials().token)
")
DATE=2026-05-27  # replace with yesterday
```

### Sleep

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/sleep/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Notes:**

---

### HRV (daily RMSSD)

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/daily-heart-rate-variability/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for rmssd:** ___________  
**Notes:**

---

### SpO2

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/oxygen-saturation/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for percentage:** ___________  
**Notes:**

---

### Respiratory Rate

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/daily-respiratory-rate/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for breaths/min:** ___________  
**Notes:**

---

### Skin Temperature Variation

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/daily-sleep-temperature-derivations/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for variation:** ___________  
**Notes:**

---

### Steps (daily rollup)

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints:dailyRollUp?startDate=${DATE}&endDate=${DATE}" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for count:** ___________  
**Notes:**

---

### Resting Heart Rate

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/daily-resting-heart-rate/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] Empty dataPoints  
**Field name for bpm:** ___________  
**Notes:**

---

### Weight

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://health.googleapis.com/v4/users/me/dataTypes/weight/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z" \
  | python -m json.tool
```

**Verdict:** [ ] Confirmed / [ ] 404 / [ ] No scale paired  
**Field name for kg:** ___________  
**Notes:**

---

### Readiness Score

Readiness Score is confirmed available on the Fitbit Air (free, via Google Health app).
API exposure status unknown — try:

```bash
# Try common data type names:
for TYPE in readiness daily-readiness readiness-score daily-readiness-score; do
  echo "--- $TYPE ---"
  curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $ACCESS_TOKEN" \
    "https://health.googleapis.com/v4/users/me/dataTypes/${TYPE}/dataPoints:list?startTime=${DATE}T00:00:00Z&endTime=${DATE}T23:59:59Z"
  echo
done
```

**Verdict:** [ ] Confirmed (type name: ___________) / [ ] Not exposed via API  
**Notes:**

---

## Mapper Updates Required

After filling in the verdicts above, update `src/mapper.py` if any field names
differ from what the fixtures assume. See the `_extract_*` helpers — each has
a list of candidate field names.

Drop any endpoint marked "404" or "Not exposed via API" — do not push zeros.
