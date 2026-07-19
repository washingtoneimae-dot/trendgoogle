# Market Arbitrage MVP Pipeline Plan

## Problem Statement
Build an **efficiency flywheel architecture** that proves how to turn expensive AI infrastructure into a high-margin, self-scaling system by separating:
1. **Heavy Parser Loop (LLM)** – Runs ONCE per new topic to extract structured configuration
2. **Automated Cron Loop (Python)** – Runs 24/7 with near-zero operational cost using fixed parameters

The MVP will validate that a vague input ("eyeing raw copper trading velocity variations in Northwest India") can be parsed once into a permanent, structured tracking profile that powers continuous, automated monitoring forever.

## Proposed Approach

### **Phase 1: One-Time Heavy Parser Loop (LLM-Powered)**
- Input vague niche concept
- Extract high-value anchor keywords (3-5 keywords optimized for signal strength)
- Retrieve exact Google Trends category ID (e.g., `1158` = Metals & Mining)
- Identify precise geographic code mapping (e.g., `IN-RJ` = Rajasthan)
- Save configuration as permanent JSON profile to local database

### **Phase 2: 24/7 Automated Cron Loop (Pure Python)**
- Load pre-compiled profiles from database
- Execute pytrends API calls with fixed parameters (no LLM overhead)
- Fetch real-time/hourly trend data with 1-day or 3-month timeframe
- Calculate Arbitrage Momentum Index (AMI) on each cycle
- Detect spike anomalies (AMI >±25%) and trigger alerts
- Log results to database for historical tracking
- Sleep with randomized intervals to mimic natural behavior

### **Phase 3: Asynchronous Maintenance & Keyword Drift Detection**
- Monitor 30-day search volume variance decay
- Flag stale profiles automatically
- Re-submit stale profiles to LLM layer ONLY for keyword refresh
- Append new secondary keywords or swap underperforming terms
- Minimal LLM cost; profile remains active during evaluation

## Todos

### Phase 1: Heavy Parser Loop (LLM-Powered Configuration)
- **phase1-parse-vague-input**: Parse "eyeing raw copper trading velocity variations in Northwest India" → extract 3-5 anchor keywords
- **phase1-extract-category-id**: Map market domain to Google Trends category ID (`1158` = Metals & Mining)
- **phase1-geocode-region**: Map "Northwest India" → precise regional code (`IN-RJ` = Rajasthan)
- **phase1-save-profile**: Persist configuration as permanent JSON profile to local database

### Phase 2: Automated Cron Loop (Pure Python, 24/7)
- **phase2-database-schema**: Create persistent tables for profiles, monitoring history, and alerts
- **phase2-setup-cron-loop**: Build continuous loop daemon with randomized sleep intervals (60-180s)
- **phase2-implement-ami-calculation**: Implement real-time AMI calculation and threshold triggers (>+25%, <-25%)
- **phase2-test-continuous-loop**: Run 48-hour stress test with Rajasthan copper profile; verify logging

### Phase 3: Drift Detection & Maintenance
- **phase3-drift-detection**: Monitor 30-day search volume variance decay; auto-flag stale profiles
- **phase3-maintenance-trigger**: Re-submit flagged profiles to LLM for keyword refresh (minimal cost)

### Phase 4: Validation & Cost Economics
- **phase4-validate-cost-efficiency**: Prove LLM cost amortizes over ~30 days of continuous monitoring
- **phase4-validate-signal-accuracy**: Backtest AMI thresholds against known market anomalies
- **phase4-document-flywheel**: Compile full architecture guide with cost model and reproducibility

## Key Decisions

### Architecture Split: Two-Loop Efficiency Flywheel
- **Heavy Loop (LLM)**: Runs ONCE per new topic. Extracts keywords, category, geography. Costs ~$0.01–$0.05 per parse.
- **Cheap Loop (Python)**: Runs 24/7. Uses fixed parameters from database. Costs ~$0 (only pytrends rate limits, no LLM).
- **ROI Inflection**: After ~30 days of continuous monitoring, LLM parsing cost is fully amortized. Profit scales linearly from there.

### Database Schema
Three persistent tables enable the flywheel:

```sql
-- Configuration profiles (one per market niche)
CREATE TABLE active_profiles (
    topic_name TEXT PRIMARY KEY,
    keywords TEXT,  -- JSON array: ["copper price", "copper scrap"]
    category INT,   -- Google Trends category ID (1158 = Metals & Mining)
    geo TEXT,       -- Geographic code (IN-RJ = Rajasthan)
    created_at TIMESTAMP,
    last_refreshed TIMESTAMP
);

-- Historical monitoring data (logged every cron cycle)
CREATE TABLE monitoring_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT,
    timestamp TIMESTAMP,
    ami_score FLOAT,       -- % velocity change
    signal_class TEXT,     -- "CRITICAL_ALERT" | "MARKET_DECAY" | "STABLE"
    raw_data TEXT,         -- JSON: {"copper price": 75, "copper scrap": 68}
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
);

-- Alert triggers (anomaly detection log)
CREATE TABLE alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT,
    timestamp TIMESTAMP,
    ami_score FLOAT,
    alert_type TEXT,  -- "HIGH_SPIKE" | "SHARP_DECLINE"
    signal_confidence FLOAT,  -- 0.0–1.0 based on consistency
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
);

-- Drift detection tracking (for Phase 3 maintenance)
CREATE TABLE drift_detection (
    topic_name TEXT PRIMARY KEY,
    volume_variance_30d FLOAT,
    is_stale BOOLEAN,
    flagged_at TIMESTAMP,
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
);
```

### Continuous Monitoring Loop Pseudocode
```python
import time
import random
import json
from pytrends.request import TrendReq
from datetime import datetime, timedelta

pytrend = TrendReq(hl='en-US', tz=360)

while True:
    # Step 1: Load all active profiles from database
    active_profiles = db.query("SELECT * FROM active_profiles")
    
    for profile in active_profiles:
        try:
            # Step 2: Fetch real-time data with fixed parameters (from database, no LLM)
            pytrend.build_payload(
                kw_list=json.loads(profile['keywords']),
                cat=profile['category'],
                timeframe='now 1-d',  # Real-time hourly data
                geo=profile['geo']
            )
            
            hourly_data = pytrend.interest_over_time()
            
            # Step 3: Calculate AMI (real-time vs. 30-day baseline)
            baseline_30d = db.query_avg_ami(profile['topic_name'], days=30)
            current_ami = calculate_ami(hourly_data, baseline_30d)
            
            # Step 4: Log result to monitoring_history
            db.insert('monitoring_history', {
                'topic_name': profile['topic_name'],
                'timestamp': datetime.now(),
                'ami_score': current_ami,
                'signal_class': classify_signal(current_ami)
            })
            
            # Step 5: Trigger alerts if >±25%
            if abs(current_ami) > 25:
                db.insert('alert_log', {
                    'topic_name': profile['topic_name'],
                    'timestamp': datetime.now(),
                    'ami_score': current_ami,
                    'alert_type': 'HIGH_SPIKE' if current_ami > 25 else 'SHARP_DECLINE'
                })
            
            # Step 6: Check for drift (Phase 3)
            volume_variance_30d = db.query_variance(profile['topic_name'], days=30)
            if volume_variance_30d < 10:
                db.flag_stale_profile(profile['topic_name'])
                # (LLM would re-evaluate keywords only when flagged)
        
        except Exception as e:
            print(f"Rate limit or error: {e}")
    
    # Step 7: Sleep with random jitter to mimic natural behavior
    time.sleep(random.randint(60, 180))
```

### Signal Classification Rules
- **AMI > +25%**: `CRITICAL_ALERT` – Asymmetric demand spike, high arbitrage potential
- **AMI < -25%**: `MARKET_DECAY` – Trend volume collapsing, avoid entry
- **AMI ∈ [-25%, +25%]**: `STABLE` – Organic baseline drift, no anomaly

## Deliverables
1. **Phase 1 Output**: Parsed configuration JSON profile for Rajasthan copper topic (keywords, category ID, geo code)
2. **Phase 2 Output**: 
   - `database_schema.sql` – SQL file defining persistent tables for profiles, history, alerts, drift detection
   - `cron_daemon.py` – Self-contained 24/7 monitoring daemon script
   - 48-hour test log showing continuous AMI calculations, signal classifications, and alert triggers
3. **Phase 3 Output**: Drift detection integration (flags stale profiles for LLM maintenance)
4. **Phase 4 Output**: 
   - Cost efficiency report: LLM parse cost vs. 30-day cron savings
   - Backtest validation: Historical accuracy of AMI thresholds
   - Full architecture guide: Reproducibility, scaling, and maintenance playbook

## Economics Model: The Efficiency Flywheel

| Phase | Cost | Duration | Cumulative |
|-------|------|----------|-----------|
| LLM Parse (1x) | $0.02 | 2 min | $0.02 |
| Cron Loop (24/7) | $0.00 | 30 days | $0.02 |
| Cron Loop (24/7) | $0.00 | 60 days | $0.02 |
| Cron Loop (24/7) | $0.00 | 1 year | $0.02 |
| LLM Refresh (1x stale) | $0.01 | 2 min | $0.03 |
| Cron Loop (24/7 cont'd) | $0.00 | ∞ | $0.03 |

**Profit Inflection**: After initial LLM parse, every 30 days of continuous monitoring costs ≈$0. Scaling to 100 topics: 100 LLM parses (~$2), then 24/7 monitoring at near-zero marginal cost. Exponential profit curve.

## Notes & Risks

- **Unofficial API**: pytrends is rate-limited and may change. Mitigation: randomized sleep intervals, lightweight payloads.
- **Low Search Volume**: Hyper-niche markets may return sparse data. Fallback: broaden geo (e.g., IN vs. IN-RJ) or keywords temporarily.
- **Keyword Drift**: Market jargon evolves. Mitigation: Phase 3 drift detection auto-flags stale profiles for LLM refresh.
- **Seasonal Patterns**: 30-day baseline may miss yearly cycles. For long-term accuracy, extend to 1-year baseline after 12 months.
- **Production Hardening**: This MVP uses local SQLite. Production would add: failover DB, alert webhooks, monitoring dashboard, error recovery.
- **Legal/TOS**: pytrends violates Google TOS. For production, use official Google Trends API or swap datasource (Yahoo Finance, Coinbase API, etc.).
