# TrendGoogle System Blueprint

## Overview
Two-tier efficiency flywheel: expensive LLM discovery ($0.02) → zero-cost 24/7 monitoring ($0/year).

```
User says "track copper in India"
        │
        ▼
 TRENDFINDER (LLM Agent)         Phase 1: One-time LLM discovery
  - Gemini API analyzes
  - Extracts keywords
  - Validates vs pytrends
  - Configures thresholds
  - Saves to DB
  Cost: ~$0.02/topic
        │ INSERT active_profile
        ▼
 SQLite Database                 Persistent storage
  - active_profiles
  - monitoring_history
  - alert_log
  - drift_detection
  - api_users / api_usage
        │ READ every cycle
        ▼
 CRON DAEMON (24/7)              Phase 2: Zero-cost monitoring
  - Fetches pytrends data
  - Calculates AMI
  - Checks per-profile thresholds
  - Logs + alerts
  Cost: $0/year
        │ API calls
        ▼
 API GATEWAY (port 8000)         Customer interface
  - Momentum data
  - Alerts
  - Asset list
  - Usage/billing
  Auth: X-API-Key
```

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `trendfinder.py` | LLM-powered trend discovery agent. Chat REPL. | 403 |
| `cron_daemon.py` | 24/7 monitoring daemon. Runs every 60-180s. | 276 |
| `api_gateway.py` | FastAPI REST API on port 8000. | 408 |
| `query_database.py` | Inspect DB contents. | 35 |
| `init_database.py` | Initialize DB schema. | 83 |
| `setup_api_users.py` | Generate API keys for customers. | 71 |
| `arbitrage_flywheel.db` | SQLite database (48KB, pre-populated). | -- |

## Database Schema (7 tables)

### active_profiles
- topic_name (TEXT PK): e.g. "rajasthan_copper_scrap"
- keywords (TEXT): JSON array of Google Trends keywords
- category (INT): Google Trends category ID (1158 = Metals & Mining)
- geo (TEXT): Country code or "" for worldwide
- created_at (TIMESTAMP)
- last_refreshed (TIMESTAMP)
- spike_threshold (REAL, default 25.0): Alert if AMI rises above this %
- drop_threshold (REAL, default -25.0): Alert if AMI drops below this %
- monitor_enabled (INT, default 1): Is this profile active?
- alert_on_spike (INT, default 1): Notify on sharp increases?
- alert_on_drop (INT, default 1): Notify on sharp drops?

### monitoring_history
- id (INTEGER PK)
- topic_name (TEXT, FK)
- timestamp (TIMESTAMP)
- ami_score (REAL): Arbitrage Momentum Index %
- signal_class (TEXT): STABLE / CRITICAL_ALERT / MARKET_DECAY
- raw_data (TEXT): JSON snapshot of raw trend values

### alert_log
- id (INTEGER PK)
- topic_name (TEXT)
- timestamp (TIMESTAMP)
- ami_score (REAL)
- alert_type (TEXT): HIGH_SPIKE / SHARP_DECLINE
- signal_confidence (REAL): 0.0-1.0

### Other
- drift_detection: topic_name, volume_variance_30d, is_stale, flagged_at
- api_users: user_id, username, api_key, tier, rate_limit, is_active
- api_usage: usage_id, user_id FK, endpoint, timestamp, response_time_ms

## Workflows

### Setup (one time)
```bash
python trendfinder.py --setup   # Enter your Gemini API key
```

### Add a trend (agent discovers + configures automatically)
```bash
python trendfinder.py
>> copper scrap India -- aggressive spike alerts
```
LLM analyzes, validates, configures, saves. No manual steps.

### Start monitoring
```bash
# Terminal 1: Daemon (24/7)
.venv/bin/python cron_daemon.py

# Terminal 2: API (for customers)
.venv/bin/uvicorn api_gateway:app --host 0.0.0.0 --port 8000
```

### Check data
```bash
python query_database.py
```

### Customer API call
```bash
curl -H "X-API-Key: sk_live_XXX" http://localhost:8000/api/v1/momentum/rajasthan_copper_scrap
```

## Key Concepts

- **AMI**: Arbitrage Momentum Index - % change from 30-day baseline. Positive = rising interest, negative = declining.
- **Signal**: STABLE (within thresholds), CRITICAL_ALERT (spike), MARKET_DECAY (sharp drop)
- **Per-profile thresholds**: Each topic has its own spike/drop levels, set by the LLM based on your wording
- **The Flywheel**: $0.02 LLM parse once → $0/year monitoring forever. ROI improves with time.
- **Cost model**: 1 topic = $0.02/year. 100 topics = $2.00/year. Monitoring costs nothing.
