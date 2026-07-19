#!/usr/bin/env python3
import sqlite3
import json

DB_PATH = 'arbitrage_flywheel.db'
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get monitoring history
print('[MONITORING HISTORY]')
cursor.execute('''
    SELECT topic_name, timestamp, ami_score, signal_class, raw_data
    FROM monitoring_history
    ORDER BY timestamp DESC
    LIMIT 10
''')

rows = cursor.fetchall()
for row in rows:
    print(f"  {row['timestamp']} | {row['topic_name']} | AMI: {row['ami_score']:+.2f}% | {row['signal_class']}")
    raw = json.loads(row['raw_data'])
    print(f"    Raw data: {raw}")

# Get alert log
print('\n[ALERT LOG]')
cursor.execute('SELECT * FROM alert_log ORDER BY timestamp DESC LIMIT 10')
alert_rows = cursor.fetchall()
if alert_rows:
    for row in alert_rows:
        print(f"  {row['timestamp']} | {row['topic_name']} | {row['alert_type']} | AMI: {row['ami_score']:+.2f}%")
else:
    print("  (No alerts triggered)")

conn.close()
