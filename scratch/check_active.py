import sys
sys.path.insert(0, '.')
import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

now_iso = datetime.now(timezone.utc).isoformat()

rows = c.execute("""
    SELECT channel_call_sign, show_title, episode_title, season_number, episode_number, air_datetime, duration, is_new
    FROM guide_airings
    WHERE channel_call_sign IN ('WTTV', 'WRTV', 'WTHR', 'WFYI-1', 'WTTK', 'WXIN', 'DYSTR')
      AND datetime(air_datetime, '+' || duration || ' seconds') >= datetime('now')
      AND datetime(air_datetime) <= datetime('now', '+6 hours')
    ORDER BY channel_call_sign, air_datetime ASC
""").fetchall()

print(f"Airings found: {len(rows)}")
grouped = {}
for r in rows:
    grouped.setdefault(r["channel_call_sign"], []).append(dict(r))

for ch, airings in grouped.items():
    print(f"\nChannel {ch} ({len(airings)} upcoming airings next 6 hrs):")
    for a in airings:
        print(f"  {a['air_datetime']} ({a['duration']//60}m): {a['show_title']} - {a['episode_title']} (New: {a['is_new']})")
