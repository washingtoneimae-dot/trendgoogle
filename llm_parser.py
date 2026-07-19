#!/usr/bin/env python3
"""
Phase 1: LLM Parser - Turns vague user prompts into structured Google Trends profiles.
Uses Gemini API to extract keywords, category, and geography.
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
    """Load key=value pairs from .env file (if exists)."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())


def get_api_key() -> str:
    """Get Gemini API key from env or .env."""
    key = os.environ.get("GEMINI_API_KEY")
    if key and key != "your-gemini-api-key-here":
        return key
    return None

# ---------------------------------------------------------------------------
# LLM: Gemini
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a keyword researcher for Google Trends arbitrage detection.

Given a vague user prompt about a market or topic they want to monitor, extract:

1. **keywords** (array of 4-6 strings): Google Trends search terms.
   CRITICAL: These must be BROAD enough to have real search volume on Google.
   Prefer terms that people actually search for daily.
   AVOID hyper-niche, overly specific, or technical jargon terms.
   Mix broad and slightly specific terms.

2. **category_id** (integer): The most relevant Google Trends category ID.
   Common categories:
   - 1158 = Metals & Mining
   - 71 = Vehicles
   - 12 = Business & Industrial
   - 132 = Finance
   - 3 = Electronics
   - 20 = Energy & Utilities
   - 1267 = Technology
   - 13 = Real Estate
   - 293 = Commodities
   - 174 = Cryptocurrency
   - 958 = Agriculture
   - 1159 = Precious Metals

3. **category_name** (string): Human-readable name of the category

4. **geo** (string): Two-letter ISO country code (e.g., "US", "IN", "KE", "GB", "DE").
   Use "" for worldwide.

5. **topic_name** (string): A short, URL-safe identifier for this profile (snake_case).

6. **confidence** (string): "high", "medium", or "low"

Return ONLY valid JSON. No markdown, no explanation."""


def parse_with_gemini(prompt: str) -> dict:
    """Call Gemini API to extract structured data from a user prompt."""
    import google.genai as genai

    load_env()
    api_key = get_api_key()
    if not api_key:
        print("[ERROR] Set GEMINI_API_KEY environment variable")
        print("  export GEMINI_API_KEY='your-key-here'")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    
    full_prompt = f"{SYSTEM_PROMPT}\n\nUser prompt: {prompt}"
    
    print(f"[LLM] Sending to Gemini 2.5 Flash...")
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

    conn.commit()
    conn.close()
    print(f"[DB] Saved profile: {topic_name}")
    print(f"  Keywords: {data['keywords']}")
    print(f"  Category: {category} ({data.get('category_name', '?')})")
    print(f"  Geo: {geo if geo else 'Worldwide'}")


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
            print(f"[WARN] All keywords returned 0 data. Try broader terms.")
            return False
        
        # Check if any keyword has non-zero values
        non_zero = False
        for kw in keywords:
            if kw in df.columns and df[kw].sum() > 0:
                non_zero = True
        
        if not non_zero:
            print(f"[WARN] Keywords exist but all values are 0 (no search volume)")
            return False
        
        print(f"[OK] Keywords validated — returning real data from Google Trends")
        return True
    
    except ImportError:
        print("[WARN] pytrends not installed, skipping validation")
        return True
    except Exception as e:
        print(f"[WARN] Validation failed: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    load_env()
    
    if len(sys.argv) < 2:
        print("Usage: python llm_parser.py <your prompt>")
        print("       python llm_parser.py --setup")
        print("")
        print("Example: python llm_parser.py 'track electric vehicle sales in Kenya'")
        sys.exit(1)
    
    if sys.argv[1] == "--setup":
        key = input("Enter your Gemini API key: ").strip()
        if key:
            ENV_PATH.write_text(f"# Gemini API key\nGEMINI_API_KEY={key}\n")
            print(f"[OK] Saved to {ENV_PATH}")
            print("You can now run: python llm_parser.py 'your topic'")
        else:
            print("[ERR] No key entered")
        sys.exit(0)
    
    prompt = " ".join(sys.argv[1:])
    print(f"[INPUT] {prompt}\n")
    
    # Step 1: LLM parses the prompt
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
