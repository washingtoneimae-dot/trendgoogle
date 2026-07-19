#!/usr/bin/env python3
"""
Phase 1: Initialize the Arbitrage Flywheel Database
Persists the parsed configuration for 24/7 monitoring daemon
"""

import sqlite3
import json
from datetime import datetime

# Database path
DB_PATH = 'arbitrage_flywheel.db'

# Connect to database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create persistent tables for the efficiency flywheel
cursor.execute('''
CREATE TABLE IF NOT EXISTS active_profiles (
    topic_name TEXT PRIMARY KEY,
    keywords TEXT NOT NULL,
    category INT NOT NULL,
    geo TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_refreshed TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS monitoring_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT NOT NULL,
    timestamp TIMESTAMP,
    ami_score REAL,
    signal_class TEXT,
    raw_data TEXT,
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT NOT NULL,
    timestamp TIMESTAMP,
    ami_score REAL,
    alert_type TEXT,
    signal_confidence REAL,
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS drift_detection (
    topic_name TEXT PRIMARY KEY,
    volume_variance_30d REAL,
    is_stale BOOLEAN DEFAULT 0,
    flagged_at TIMESTAMP,
    FOREIGN KEY(topic_name) REFERENCES active_profiles(topic_name)
)
''')

# Insert the parsed Rajasthan copper profile
keywords = json.dumps(["copper price", "copper scrap", "copper trading", "raw copper"])
cursor.execute('''
INSERT OR REPLACE INTO active_profiles (topic_name, keywords, category, geo, created_at)
VALUES (?, ?, ?, ?, ?)
''', ('rajasthan_copper_scrap', keywords, 1158, 'IN-RJ', datetime.now()))

# Initialize drift detection tracking
cursor.execute('''
INSERT OR REPLACE INTO drift_detection (topic_name, is_stale)
VALUES (?, ?)
''', ('rajasthan_copper_scrap', 0))

conn.commit()
conn.close()

print("[OK] Database initialized successfully")
print(f"[DB] Database: {DB_PATH}")
print("[SCHEMA] Tables created: active_profiles, monitoring_history, alert_log, drift_detection")
print("[PROFILE] rajasthan_copper_scrap inserted")
print(f"   Keywords: ['copper price', 'copper scrap', 'copper trading', 'raw copper']")
print(f"   Category: 1158 (Metals & Mining)")
print(f"   Geo: IN-RJ (Rajasthan, India)")
