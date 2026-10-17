import asyncio
import sqlite3
import httpx
from app.tablo_client import tablo_manager
from app.config import IMAGE_CACHE_DIR

tablo_manager.load_cached_config()

async def cache_all_scheduled_and_highlights():
    conn = sqlite3.connect('data/tablo_cache.db')
    conn.row_factory = sqlite3.Row
    
    # 1. All scheduled series
    scheduled = conn.execute("SELECT path, title, cover_url, backdrop_url FROM guide_shows WHERE schedule_rule IN ('new', 'all')").fetchall()
    # 2. All primetime / premiere shows
    highlights = conn.execute("SELECT DISTINCT g.path, g.title, g.cover_url, g.backdrop_url FROM guide_shows g JOIN guide_airings a ON g.path = a.series_path WHERE a.is_primetime = 1 OR a.is_premiere = 1").fetchall()
    
    all_shows = {r['path']: dict(r) for r in (scheduled + highlights)}.values()
    print(f"Total shows to pre-cache: {len(all_shows)}")
    
    image_ids = set()
    for s in all_shows:
        for key in ('cover_url', 'backdrop_url'):
            u = s.get(key)
            if u and '/api/images/' in u:
                img_id = u.split('/')[-1].split('?')[0]
                if img_id.isdigit():
                    image_ids.add(img_id)
                    
    print(f"Total unique images to pre-cache: {len(image_ids)}")
    
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        sem = asyncio.Semaphore(10)
        async def fetch_one(img_id):
            target = IMAGE_CACHE_DIR / f"{img_id}.jpg"
            if target.exists() and target.stat().st_size > 0:
                return True
            async with sem:
                url = f"{tablo_manager.device.local_url.rstrip('/')}/images/{img_id}"
                try:
                    r = await client.get(url)
                    if r.status_code == 200 and len(r.content) > 0:
                        target.write_bytes(r.content)
                        return True
                    else:
                        print(f"Failed {img_id}: HTTP {r.status_code}")
                except Exception as e:
                    print(f"Error {img_id}: {e}")
            return False

        results = await asyncio.gather(*(fetch_one(img_id) for img_id in image_ids))
        success = sum(1 for r in results if r)
        print(f"Successfully cached {success} / {len(image_ids)} images locally!")

asyncio.run(cache_all_scheduled_and_highlights())
