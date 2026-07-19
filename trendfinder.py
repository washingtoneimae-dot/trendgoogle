#!/usr/bin/env python3
"""
Phase 1: LLM Trend Analyzer — Takes a vague user prompt, researches and analyzes
potential high-value trends, returns enriched data including predicted search
volume, seasonality, and suggested strategies.
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
# MASTER PROMPT — The full system instruction for the LLM analyst
# ---------------------------------------------------------------------------

MASTER_PROMPT = """You are an elite market trend analyst AI. Your job is to analyze a user's vague prompt and return a structured data packet that is genuinely useful and actionable.

Your mission:
1. Determine what SPECIFIC, HIGH-VALUE items/niches/topics the user can monitor for arbitrage or market advantage.
2. Find keywords that have REAL Google search volume (not technical jargon, not zero-volume terms).
3. Return not just the keywords, but the insights that make them valuable.

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
  }
}

RULES:
- PREFER keywords with actual search volume. Do people realistically type this into Google?
- ALWAYS provide analysis. Raw keywords alone are not enough.
- If no single country is obvious, use geo="" for worldwide.
- topic_name must be a valid, unique, URL-safe snake_case identifier.
- If the user asks something too vague or impossible, explain why and suggest an alternative.
- Return ONLY valid JSON. No markdown fences, no text outside the JSON."""


# ---------------------------------------------------------------------------
# LLM: Gemini
# ---------------------------------------------------------------------------

def parse_with_gemini(prompt: str) -> dict:
    """Call Gemini API to extract structured data from a user prompt."""
    import google.genai as genai

    load_env()
    api_key = get_api_key()
    if not api_key:
        print("[ERROR] Set GEMINI_API_KEY environment variable")
        print("  export GEMINI_API_KEY='your-key-here'")
        print("  Or run: python trendfinder.py --setup")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    full_prompt = f"{MASTER_PROMPT}\n\nUser prompt: {prompt}"

    print(f"[LLM] Analyzing with Gemini 2.5 Flash...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=full_prompt,
        config={
            "response_mime_type": "application/json",
        }
    )

    raw = response.text.strip()
    # Strip markdown code fences if Gemini wraps it
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    result = json.loads(raw)
    return result


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def save_profile(data: dict):
    """Save parsed profile to SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    keywords_json = json.dumps(data["keywords"])
    topic_name = data["topic_name"]
    category = data["category_id"]
    geo = data.get("geo", "")
    analysis = data.get("analysis", {})

    cursor.execute('''
        INSERT OR REPLACE INTO active_profiles
        (topic_name, keywords, category, geo, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (topic_name, keywords_json, category, geo, datetime.now()))

    cursor.execute('''
        INSERT OR REPLACE INTO drift_detection
        (topic_name, is_stale)
        VALUES (?, 0)
    ''', (topic_name,))

    # Store the analysis as metadata — add a notes column if possible,
    # or just log it to console
    conn.commit()
    conn.close()

    print(f"[DB] Saved profile: {topic_name}")
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


# ---------------------------------------------------------------------------
# Keyword validation
# ---------------------------------------------------------------------------

def validate_keywords(data: dict) -> bool:
    """Quick-check if keywords return any real data from pytrends."""
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

        # Check if any keyword has non-zero values
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
        return True  # Don't block save on validation error


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    load_env()

    if len(sys.argv) < 2:
        print("Usage: python trendfinder.py <your prompt>")
        print("       python trendfinder.py --setup")
        print("")
        print("Examples:")
        print("  python trendfinder.py 'electric vehicle battery prices in Kenya'")
        print("  python trendfinder.py 'track AI freelancing rates globally'")
        print("  python trendfinder.py 'copper scrap arbitrage india rajasthan'")
        sys.exit(1)

    if sys.argv[1] == "--setup":
        key = input("Enter your Gemini API key: ").strip()
        if key:
            ENV_PATH.write_text(f"# Gemini API key\nGEMINI_API_KEY={key}\n")
            print(f"[OK] Saved to {ENV_PATH}")
            print("You can now run: python trendfinder.py 'your topic'")
        else:
            print("[ERR] No key entered")
        sys.exit(0)

    prompt = " ".join(sys.argv[1:])
    print(f"[INPUT] {prompt}\n")

    # Step 1: LLM analyzes and returns enriched data
    result = parse_with_gemini(prompt)
    print(f"\n[LLM RESULT]")
    print(json.dumps(result, indent=2))

    # Step 2: Validate keywords return real data
    print(f"\n{'='*50}")
    print("[STEP] Validating keywords against Google Trends...")
    if not validate_keywords(result):
        print("\n[RETRY] Keywords failed validation.")
        print("Tip: The LLM chose terms with no search volume.")
        print("Run again with a broader topic, or edit keywords manually.")
        sys.exit(1)

    # Step 3: Save to database
    print(f"\n{'='*50}")
    print("[STEP] Saving to database...")
    save_profile(result)

    print(f"\n{'='*50}")
    print("[DONE] Profile added. The daemon will pick it up on next cycle.")
    print(f"  Check data with: python query_database.py")


if __name__ == "__main__":
    main()
