import sqlite3
import json

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT * FROM episodes WHERE title LIKE '%Battles Part 2%'").fetchall()
print(f"Matches in episodes table: {len(rows)}")
for r in rows:
    d = dict(r)
    print("--------------------------------------------------")
    print(f"ID: {d['id']} | Path: {d['path']} | Show ID: {d['show_id']}")
    print(f"Title: {d['title']} | Season: {d['season_number']} | Episode: {d['episode_number']}")
    print(f"Channel: {d.get('channel_network')} | Call Sign: {d.get('channel_call_sign')} | Channel #{d.get('channel_major')}.{d.get('channel_minor')}")
    print(f"Air Date: {d.get('air_date')} | Duration: {d.get('duration')} | Status: {d.get('status')}")
    raw = json.loads(d.get('raw_json') or '{}')
    print("Channel Object:", json.dumps(raw.get('channel'), indent=2))
    print("Airing Object:", json.dumps(raw.get('airing'), indent=2))
    print("Video Object:", json.dumps(raw.get('video'), indent=2))
