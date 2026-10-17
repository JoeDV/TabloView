import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row
now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
print('Current UTC time:', now_iso)

# In SQLite, find airings that cover current time
rows = conn.execute('''
    SELECT channel_network, channel_call_sign, show_title, episode_title, season_number, episode_number, air_datetime, duration
    FROM guide_airings
    WHERE datetime(air_datetime) <= datetime(?) AND datetime(air_datetime, '+' || duration || ' seconds') >= datetime(?)
    ORDER BY channel_call_sign ASC
''', (now_iso, now_iso)).fetchall()

print(f'On Now right now across channels: {len(rows)}')
for r in rows:
    print(f"[{r['channel_call_sign']} - {r['channel_network']}] {r['show_title']} ({r['episode_title']}) | {r['air_datetime']} ({r['duration']}s)")
