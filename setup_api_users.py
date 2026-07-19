#!/usr/bin/env python3
"""
Setup API Users Table
Adds user management to the existing arbitrage_flywheel.db
Generates secure API keys for external users
"""

import sqlite3
import secrets
import json

DB_PATH = 'arbitrage_flywheel.db'

def setup_api_users():
    """Create api_users table and insert test user with API key"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table for users and their API keys
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        tier TEXT DEFAULT 'sandbox',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        rate_limit_requests INTEGER DEFAULT 1000,
        rate_limit_period_minutes INTEGER DEFAULT 60,
        is_active BOOLEAN DEFAULT 1
    )
    ''')
    
    # Create table for API usage tracking (for billing)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_usage (
        usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        endpoint TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        response_time_ms FLOAT,
        FOREIGN KEY(user_id) REFERENCES api_users(user_id)
    )
    ''')
    
    # Generate a test user with a secure API key
    test_key = f"sk_live_{secrets.token_urlsafe(24)}"
    try:
        cursor.execute(
            "INSERT INTO api_users (username, api_key, tier) VALUES (?, ?, ?)", 
            ('test_arbitrageur', test_key, 'pro')
        )
        conn.commit()
        print("[OK] API Users table created")
        print("[OK] Test user created")
        print(f"\n[API_KEY] sk_live_{test_key.split('sk_live_')[1]}")
        print(f"[USERNAME] test_arbitrageur")
        print(f"[TIER] pro")
        print(f"\nUse this API key in the X-API-Key header for all requests.")
        
    except sqlite3.IntegrityError:
        print("[INFO] User already exists. Using existing API key.")
        cursor.execute("SELECT api_key, tier FROM api_users WHERE username = ?", ('test_arbitrageur',))
        row = cursor.fetchone()
        if row:
            print(f"[API_KEY] {row[0]}")
            print(f"[TIER] {row[1]}")
    
    conn.close()

if __name__ == '__main__':
    setup_api_users()
