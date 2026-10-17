import sqlite3
import json

conn = sqlite3.connect('data/tablo_cache.db')
conn.row_factory = sqlite3.Row

print('=== GUIDE SHOWS ===')
rows = conn.execute("SELECT path, title, cover_url, backdrop_url, raw_json FROM guide_shows WHERE title LIKE '%9-1-1%' OR title LIKE '%911%'").fetchall()
for r in rows:
    print(r['path'], '|', r['title'], '| cover:', r['cover_url'], '| backdrop:', r['backdrop_url'])
    raw = json.loads(r['raw_json'])
    series_obj = raw.get('series', {})
    images = {k: v for k, v in series_obj.items() if 'image' in k}
    print('  images:', images)

print('\n=== RECORDINGS / SERIES ===')
rows2 = conn.execute("SELECT path, title, cover_url, backdrop_url, raw_json FROM series WHERE title LIKE '%9-1-1%' OR title LIKE '%911%'").fetchall()
for r in rows2:
    print(r['path'], '|', r['title'], '| cover:', r['cover_url'], '| backdrop:', r['backdrop_url'])
    raw = json.loads(r['raw_json'])
    series_obj = raw.get('series', {})
    images = {k: v for k, v in series_obj.items() if 'image' in k}
    print('  images:', images)

print('\n=== AIRINGS FOR 9-1-1 ===')
rows3 = conn.execute("SELECT path, series_path, show_title, episode_title, season_number, episode_number FROM guide_airings WHERE show_title LIKE '%9-1-1%' LIMIT 5").fetchall()
for r in rows3:
    print(r['path'], '|', r['show_title'], '| S', r['season_number'], 'E', r['episode_number'], '|', r['episode_title'])
