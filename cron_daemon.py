#!/usr/bin/env python3
"""
Phase 2: Arbitrage Flywheel - 24/7 Automated Cron Loop Daemon
Runs continuously, fetching real-time trend data and calculating AMI (Arbitrage Momentum Index)
Zero LLM overhead - uses fixed parameters from database
"""

import sqlite3
import json
import time
import random
from datetime import datetime, timedelta
from pytrends.request import TrendReq

# Database path (OneDrive folder)
DB_PATH = r'C:\Users\someone\OneDrive\Documents\New folder (2)\arbitrage_flywheel.db'

# TrendReq instance
pytrend = TrendReq(hl='en-US', tz=360)

def load_active_profiles():
    """Load all active profiles from database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM active_profiles WHERE topic_name != ""')
    profiles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return profiles

def fetch_trend_data(profile):
    """Fetch real-time trend data from pytrends"""
    try:
        keywords = json.loads(profile['keywords'])
        
        # Build payload with 24-hour window for real-time velocity
        pytrend.build_payload(
            kw_list=keywords,
            cat=profile['category'],
            timeframe='now 1-d',  # Last 24 hours (real-time granularity)
            geo=profile['geo']
        )
        
        # Fetch interest over time
        df = pytrend.interest_over_time()
        
        if df.empty:
            print(f"[WARNING] No data for {profile['topic_name']}")
            return None
        
        return df
    
    except Exception as e:
        print(f"[ERROR] Fetch failed for {profile['topic_name']}: {str(e)}")
        return None

def calculate_ami(profile, current_data):
    """
    Calculate Arbitrage Momentum Index (AMI)
    AMI = % change from 30-day baseline to current 24h average
    """
    try:
        keywords = json.loads(profile['keywords'])
        
        # If multiple keywords, average them
        if len(keywords) > 1:
            combined = current_data[keywords].mean(axis=1)
        else:
            combined = current_data[keywords[0]]
        
        # Current 24h average
        current_avg = combined.mean()
        
        # Query 30-day historical baseline from database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get average from last 30 days of monitoring history
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute('''
            SELECT AVG(ami_score) as baseline
            FROM monitoring_history
            WHERE topic_name = ? AND timestamp > ?
        ''', (profile['topic_name'], thirty_days_ago))
        
        result = cursor.fetchone()
        baseline_avg = result[0] if result[0] else current_avg
        conn.close()
        
        # Calculate AMI percentage change
        if baseline_avg > 0:
            ami_score = ((current_avg - baseline_avg) / baseline_avg) * 100
        else:
            ami_score = 0.0
        
        return ami_score
    
    except Exception as e:
        print(f"[ERROR] AMI calculation failed: {str(e)}")
        return 0.0

def classify_signal(ami_score):
    """Classify signal based on AMI threshold"""
    if ami_score > 25:
        return "CRITICAL_ALERT"
    elif ami_score < -25:
        return "MARKET_DECAY"
    else:
        return "STABLE"

def log_monitoring_result(profile, current_data, ami_score, signal_class):
    """Log monitoring result to database"""
    try:
        keywords = json.loads(profile['keywords'])
        
        # Create raw data snapshot
        raw_snapshot = {}
        for kw in keywords:
            if kw in current_data.columns:
                raw_snapshot[kw] = float(current_data[kw].iloc[-1])  # Last value
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO monitoring_history (topic_name, timestamp, ami_score, signal_class, raw_data)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            profile['topic_name'],
            datetime.now(),
            ami_score,
            signal_class,
            json.dumps(raw_snapshot)
        ))
        conn.commit()
        conn.close()
        
        print(f"[LOGGED] {profile['topic_name']} | AMI: {ami_score:+.2f}% | Signal: {signal_class}")
    
    except Exception as e:
        print(f"[ERROR] Failed to log result: {str(e)}")

def trigger_alert(profile, ami_score, signal_class):
    """Trigger and log alert if anomaly detected"""
    try:
        if abs(ami_score) > 25:
            alert_type = "HIGH_SPIKE" if ami_score > 25 else "SHARP_DECLINE"
            signal_confidence = min(abs(ami_score) / 100, 1.0)  # 0.0-1.0
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alert_log (topic_name, timestamp, ami_score, alert_type, signal_confidence)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                profile['topic_name'],
                datetime.now(),
                ami_score,
                alert_type,
                signal_confidence
            ))
            conn.commit()
            conn.close()
            
            print(f"[ALERT] {alert_type} | {profile['topic_name']} | AMI: {ami_score:+.2f}%")
    
    except Exception as e:
        print(f"[ERROR] Alert trigger failed: {str(e)}")

def check_drift_detection(profile):
    """Check 30-day variance for drift (Phase 3 preparation)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get variance over last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute('''
            SELECT AVG(ami_score) as mean, 
                   (SELECT sqrt(avg((ami_score - (SELECT AVG(ami_score) FROM monitoring_history 
                    WHERE topic_name = ? AND timestamp > ?)) * (ami_score - (SELECT AVG(ami_score) FROM monitoring_history 
                    WHERE topic_name = ? AND timestamp > ?)))) as variance)
            FROM monitoring_history
            WHERE topic_name = ? AND timestamp > ?
        ''', (profile['topic_name'], thirty_days_ago, profile['topic_name'], thirty_days_ago, 
              profile['topic_name'], thirty_days_ago))
        
        result = cursor.fetchone()
        
        # Update drift detection table
        is_stale = result[0] < 10 if result[0] else False
        cursor.execute('''
            UPDATE drift_detection
            SET volume_variance_30d = ?, is_stale = ?
            WHERE topic_name = ?
        ''', (result[0] if result[0] else 0, is_stale, profile['topic_name']))
        
        conn.commit()
        conn.close()
        
        if is_stale:
            print(f"[DRIFT] {profile['topic_name']} flagged as STALE (variance < 10%)")
    
    except Exception as e:
        print(f"[WARNING] Drift detection failed: {str(e)}")

def run_monitoring_cycle():
    """Execute one complete monitoring cycle"""
    print(f"\n[CYCLE] Starting at {datetime.now().isoformat()}")
    
    profiles = load_active_profiles()
    
    if not profiles:
        print("[ERROR] No active profiles loaded")
        return
    
    for profile in profiles:
        print(f"\n[PROCESSING] {profile['topic_name']}")
        
        # Step 1: Fetch real-time trend data
        current_data = fetch_trend_data(profile)
        if current_data is None:
            continue
        
        # Step 2: Calculate AMI
        ami_score = calculate_ami(profile, current_data)
        signal_class = classify_signal(ami_score)
        
        # Step 3: Log results
        log_monitoring_result(profile, current_data, ami_score, signal_class)
        
        # Step 4: Trigger alerts if needed
        trigger_alert(profile, ami_score, signal_class)
        
        # Step 5: Check drift detection
        check_drift_detection(profile)

def run_daemon(test_cycles=None):
    """
    Main daemon loop
    If test_cycles is specified, run that many cycles then exit (for testing)
    Otherwise, run forever
    """
    print(f"[DAEMON] Starting Arbitrage Flywheel Daemon")
    print(f"[CONFIG] Database: {DB_PATH}")
    print(f"[CONFIG] Testing mode: {test_cycles is not None}")
    
    cycle_count = 0
    
    while True:
        try:
            run_monitoring_cycle()
            cycle_count += 1
            
            if test_cycles and cycle_count >= test_cycles:
                print(f"\n[TEST] Completed {test_cycles} cycles. Exiting test mode.")
                break
            
            # Sleep with randomized jitter (60-180 seconds)
            sleep_duration = random.randint(60, 180)
            print(f"[SLEEP] Sleeping for {sleep_duration}s before next cycle...")
            time.sleep(sleep_duration)
        
        except KeyboardInterrupt:
            print("\n[DAEMON] Interrupted by user. Shutting down.")
            break
        except Exception as e:
            print(f"[FATAL] Daemon error: {str(e)}")
            time.sleep(60)  # Wait before retry

if __name__ == '__main__':
    import sys
    
    # Test mode: run X cycles then exit (for validation)
    test_cycles = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    run_daemon(test_cycles=test_cycles)
