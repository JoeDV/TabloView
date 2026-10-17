import sqlite3
import json

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT id, path, raw_json FROM episodes WHERE id IN ('ep_304402', 'ep_299144')").fetchall()
for r in rows:
    print(f"=== {r['id']} ({r['path']}) ===")
    raw = json.loads(r['raw_json'] or '{}')
    print(json.dumps(raw, indent=2))
