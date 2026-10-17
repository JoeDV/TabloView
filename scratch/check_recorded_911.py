import sqlite3
import json

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row

print('=== RECORDINGS (shows table) ===')
rows = conn.execute("SELECT * FROM shows WHERE title LIKE '%9-1-1%' OR title LIKE '%911%'").fetchall()
for r in rows:
    d = dict(r)
    raw = json.loads(d.get('raw_json') or '{}')
    print('Path:', d['path'])
    print('Title:', d['title'])
    print('Category:', d['category'])
    print('cover_url:', d['cover_url'])
    print('backdrop_url:', d['backdrop_url'])
    print('thumbnail_url:', d.get('thumbnail_url'))
    print('Raw series:', json.dumps(raw.get('series', {}), indent=2))
print('Total matching in shows:', len(rows))
