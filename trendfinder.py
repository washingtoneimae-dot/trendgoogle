#!/usr/bin/env python3
"""
Phase 1: LLM Trend Analyzer — Takes a vague user prompt, researches and analyzes
potential high-value trends, then asks: "Do you want to monitor this? And what
specific conditions do you care about?"
Uses Gemini API.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = 'arbitrage_flywheel.db'

# ---------------------------------------------------------------------------
# Config: Load .env if present
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).parent / '.env'


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())


def get_api_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if key and key != "your-gemini-api-key-here":
        return key
    return None


# ---------------------------------------------------------------------------
# MASTER PROMPT
# ---------------------------------------------------------------------------

MASTER_PROMPT = """You are an elite market trend analyst AI. Your job is to analyze a user's vague prompt and return a structured data packet that is genuinely useful and actionable.

Your mission:
1. Determine what SPECIFIC, HIGH-VALUE items/niches/topics the user can monitor for arbitrage or market advantage.
2. Find keywords that have REAL Google search volume (not hyper-niche zero-volume junk).
3. Return not just the keywords, but the insights AND automatically configure monitoring based on the user's tone.

Here is what your OUTPUT must include:

{
  "topic_name": "short_snake_case_identifier",
  "category_id": int,
  "category_name": "string",
  "geo": "two-letter ISO country code or empty string for worldwide",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "analysis": {
    "volume_estimate": "low|medium|high",
    "trend_direction": "rising|surging|stable|falling",
    "arbitrage_potential": "low|medium|high",
    "competition_level": "low|medium|high",
    "optimal_season": "string describing best time of year",
    "suggested_strategy": "string: what someone should do with this insight"
  },
  "alert_config": {
    "spike_threshold": 25.0,
    "drop_threshold": -25.0,
    "alert_on_spike": true,
    "alert_on_drop": true
  }
}

For alert_config, interpret the user's INTENT:
- If they say things like "aggressive", "jumps", "surge", "spike" → use lower spike_threshold (10-15)
- If they say "crash", "drop", "decline", "decay" → use less negative drop_threshold (-10 to -15)
- If they say "conservative", "slow", "gradual" → use wider thresholds (30-40)
- If they say "monitor silently", "just track" → set both to false
- If they mention specific numbers like "30 percent" → use those
- Default: spike 25, drop -25

RULES:
- PREFER keywords with actual search volume. Do people realistically type this into Google?
- ALWAYS provide analysis and alert_config. The user should not have to configure anything manually.
- If no single country is obvious, use geo="" for worldwide.
- topic_name must be a valid, unique, URL-safe snake_case identifier.
- If the user asks something impossible, explain why and suggest an alternative.
- Return ONLY valid JSON. No markdown fences, no text outside the JSON."""


# ---------------------------------------------------------------------------
# LLM: Gemini
# ---------------------------------------------------------------------------
def parse_with_gemini(prompt: str, model_name: str = "gemini-3.1-flash-lite") -> dict:
    """Call Gemini API to extract structured data from a user prompt."""
    import google.genai as genai

    load_env()
    api_key = get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set. Run `python trendfinder.py --setup` to configure it.")

    client = genai.Client(api_key=api_key)
    full_prompt = f"{MASTER_PROMPT}\n\nUser prompt: {prompt}"

    print(f"[LLM] Analyzing with {model_name}...")
    response = client.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config={"response_mime_type": "application/json"}
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def ensure_alert_config_columns():
    """Add alert config columns if they don't exist (schema migration)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if columns exist
    c.execute("PRAGMA table_info(active_profiles)")
    cols = {row[1] for row in c.fetchall()}

    migrations = []
    if "spike_threshold" not in cols:
        migrations.append("ALTER TABLE active_profiles ADD COLUMN spike_threshold REAL DEFAULT 25.0")
    if "drop_threshold" not in cols:
        migrations.append("ALTER TABLE active_profiles ADD COLUMN drop_threshold REAL DEFAULT -25.0")
    if "monitor_enabled" not in cols:
        migrations.append("ALTER TABLE active_profiles ADD COLUMN monitor_enabled INTEGER DEFAULT 1")
    if "alert_on_spike" not in cols:
        migrations.append("ALTER TABLE active_profiles ADD COLUMN alert_on_spike INTEGER DEFAULT 1")
    if "alert_on_drop" not in cols:
        migrations.append("ALTER TABLE active_profiles ADD COLUMN alert_on_drop INTEGER DEFAULT 1")

    for sql in migrations:
        c.execute(sql)
        print(f"  [DB] Added column: {sql.split()[-1].split('(')[0]}")

    conn.commit()
    conn.close()


def save_profile(data: dict, alert_config: dict):
    """Save parsed profile with user's alert preferences."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    keywords_json = json.dumps(data["keywords"])
    topic_name = data["topic_name"]
    category = data["category_id"]
    geo = data.get("geo", "")
    analysis = data.get("analysis", {})

    cursor.execute('''
        INSERT OR REPLACE INTO active_profiles
        (topic_name, keywords, category, geo, created_at,
         spike_threshold, drop_threshold, monitor_enabled,
         alert_on_spike, alert_on_drop)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        topic_name, keywords_json, category, geo, datetime.now(),
        alert_config.get("spike_threshold", 25.0),
        alert_config.get("drop_threshold", -25.0),
        1 if alert_config.get("monitor", True) else 0,
        1 if alert_config.get("alert_on_spike", True) else 0,
        1 if alert_config.get("alert_on_drop", True) else 0,
    ))

    cursor.execute('''
        INSERT OR REPLACE INTO drift_detection (topic_name, is_stale)
        VALUES (?, 0)
    ''', (topic_name,))

    conn.commit()
    conn.close()

    print(f"\n  [DB] Saved profile: {topic_name}")
    print(f"  Keywords: {data['keywords']}")
    print(f"  Category: {category} ({data.get('category_name', '?')})")
    print(f"  Geo: {geo if geo else 'Worldwide'}")
    if analysis:
        print(f"\n  --- Market Analysis ---")
        print(f"  Volume:      {analysis.get('volume_estimate', '?')}")
        print(f"  Trend:       {analysis.get('trend_direction', '?')}")
        print(f"  Arbitrage:   {analysis.get('arbitrage_potential', '?')}")
        print(f"  Competition: {analysis.get('competition_level', '?')}")
        print(f"  Season:      {analysis.get('optimal_season', '?')}")
        print(f"  Strategy:    {analysis.get('suggested_strategy', '?')}")

    print(f"\n  --- Alert Config ---")
    print(f"  Monitor enabled:  {'Yes' if alert_config.get('monitor', True) else 'No'}")
    print(f"  Alert on spike:   {'Yes' if alert_config.get('alert_on_spike', True) else 'No'} (threshold: > +{alert_config.get('spike_threshold', 25)}% AMI)")
    print(f"  Alert on drop:    {'Yes' if alert_config.get('alert_on_drop', True) else 'No'} (threshold: < {alert_config.get('drop_threshold', -25)}% AMI)")


# ---------------------------------------------------------------------------
# Keyword validation
# ---------------------------------------------------------------------------

def validate_keywords(data: dict) -> bool:
    try:
        from pytrends.request import TrendReq
        pytrend = TrendReq(hl='en-US', tz=360)

        keywords = data["keywords"]
        category = data["category_id"]
        geo = data.get("geo", "")

        pytrend.build_payload(
            kw_list=keywords,
            cat=category,
            timeframe='now 7-d',
            geo=geo
        )
        df = pytrend.interest_over_time()

        if df.empty:
            print(f"  [WARN] All keywords returned 0 data. Try broader terms.")
            return False

        for kw in keywords:
            if kw in df.columns and df[kw].sum() > 0:
                print(f"  [OK] Keywords validated — returning real data from Google Trends")
                return True

        print(f"  [WARN] Keywords exist but all values are 0 (no search volume)")
        return False

    except ImportError:
        print("  [WARN] pytrends not installed, skipping validation")
        return True
    except Exception as e:
        print(f"  [WARN] Validation skipped: {e}")
        return True


# ---------------------------------------------------------------------------
# Interactive flow: ask user what they want to monitor
# ---------------------------------------------------------------------------

def prompt_alert_config(data: dict) -> dict:
    """Ask the user what they want to track and how."""
    analysis = data.get("analysis", {})
    strategy = analysis.get("suggested_strategy", "")

    print(f"\n{'='*60}")
    print(f"  FOUND: {data['topic_name']}")
    print(f"  Keywords: {', '.join(data['keywords'])}")
    print(f"  Volume: {analysis.get('volume_estimate','?')} | "
          f"Trend: {analysis.get('trend_direction','?')} | "
          f"Arbitrage: {analysis.get('arbitrage_potential','?')}")
    if strategy:
        print(f"  Suggestion: {strategy}")
    print(f"{'='*60}")

    # Ask if they want to monitor
    resp = input("\n  Do you want to monitor these keywords? (Y/n): ").strip().lower()
    if resp == 'n':
        print("  Skipped. Run trendfinder.py again with a different topic.")
        sys.exit(0)

    config = {"monitor": True}

    # Ask what they care about
    print("\n  What specific conditions do you want alerts for?")
    print("  (Press Enter to accept defaults)")

    spike = input("  Alert on SHARP INCREASE? (Y/n): ").strip().lower()
    config["alert_on_spike"] = spike != 'n'

    if config["alert_on_spike"]:
        spike_val = input("  Increase threshold in % (default 25): ").strip()
        config["spike_threshold"] = float(spike_val) if spike_val else 25.0
    else:
        config["spike_threshold"] = 25.0

    drop = input("  Alert on SHARP DROP? (Y/n): ").strip().lower()
    config["alert_on_drop"] = drop != 'n'

    if config["alert_on_drop"]:
        drop_val = input("  Drop threshold in % (default -25): ").strip()
        config["drop_threshold"] = float(drop_val) if drop_val else -25.0
    else:
        config["drop_threshold"] = -25.0

    return config


# ---------------------------------------------------------------------------
# CLI: Chat REPL
# ---------------------------------------------------------------------------

def chat_loop():
    """Interactive chat loop — like talking to a trend analyst."""
    print(f"\n{'='*60}")
    print("  TRENDFINDER — Market Trend Discovery Chat")
    print(f"{'='*60}")
    print("  Describe a market, niche, or topic you want to track.")
    print("  Include any preferences (aggressive, conservative, etc.)")
    print("  The AI configures everything automatically.")
    print("  Examples:")
    print("    'copper scrap trading India — aggressive spike alerts'")
    print("    'electric vehicle batteries in Kenya, just monitor quietly'")
    print("    'bitcoin mining profitability — alert me on any big drop'")
    print("    'quit' to exit")
    print(f"{'='*60}\n")

    ensure_alert_config_columns()

    while True:
        try:
            prompt = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not prompt:
            continue
        if prompt.lower() in ('quit', 'exit', 'q'):
            print("Goodbye.")
            break

        print()

        # Step 1: LLM analyzes + configures everything
        result = parse_with_gemini(prompt)
        print(f"\n[LLM RESULT]")
        print(json.dumps(result, indent=2))

        # Step 2: Validate keywords
        print(f"\n{'='*50}")
        print("[STEP] Validating keywords against Google Trends...")
        valid = validate_keywords(result)
        if not valid:
            print("\n  Those keywords returned no data. Try a broader topic.\n")
            continue

        # Step 3: Extract alert config from LLM output (auto mode)
        alert_config = result.get("alert_config", {})
        if not alert_config:
            # Fallback: manual config if LLM didn't provide it
            print("\n  [LLM didn't configure alerts. Manual setup:]")
            alert_config = prompt_alert_config(result)
        else:
            print(f"\n  [AI Auto-Configured Alerts] ✓")

        # Step 4: Save
        print(f"\n{'='*50}")
        print("[STEP] Saving to database...")
        save_profile(result, alert_config)

        # Step 5: AI gives a natural feedback summary
        analysis = result.get("analysis", {})
        ac = alert_config
        print(f"\n{'='*60}")
        print(f"  ✅ DONE — {result['topic_name']} is now active!")
        print(f"  Keywords: {', '.join(result['keywords'])}")
        print(f"  Region:   {result.get('geo', 'Worldwide')}")
        print(f"  Volume:   {analysis.get('volume_estimate', '?')}")
        if ac.get("alert_on_spike"):
            print(f"  🔺 Spike alert: > +{ac['spike_threshold']}% AMI")
        if ac.get("alert_on_drop"):
            print(f"  🔻 Drop alert:  < {ac['drop_threshold']}% AMI")
        if analysis.get("suggested_strategy"):
            print(f"\n  💡 {analysis['suggested_strategy']}")
        print(f"{'='*60}")
        print(f"\n  Type another topic or 'quit' to exit.\n")


def main():
    load_env()

    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        key = input("Enter your Gemini API key: ").strip()
        if key:
            ENV_PATH.write_text(f"# Gemini API key\nGEMINI_API_KEY={key}\n")
            print(f"[OK] Saved to {ENV_PATH}")
            print("Run: python trendfinder.py")
        else:
            print("[ERR] No key entered")
        sys.exit(0)

    # Start the chat loop
    chat_loop()


if __name__ == "__main__":
    main()
