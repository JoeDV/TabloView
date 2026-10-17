import sqlite3

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT path, title, schedule_rule, cover_url, backdrop_url FROM guide_shows WHERE schedule_rule IN ('new', 'all')").fetchall()
print('Scheduled in DB:', len(rows))
for r in rows:
    print(r['title'], '|', r['schedule_rule'], '| cover:', r['cover_url'], '| backdrop:', r['backdrop_url'])
