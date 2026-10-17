import asyncio
import sqlite3
import httpx
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()

async def test():
    conn = sqlite3.connect('data/tablo_cache.db')
    rows = conn.execute("SELECT path, title, cover_url FROM guide_shows WHERE cover_url IS NOT NULL ORDER BY RANDOM() LIMIT 10").fetchall()
    
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as no_redir_client:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as redir_client:
            for path, title, cover_url in rows:
                img_id = cover_url.split('/')[-1]
                url = f"{tablo_manager.device.local_url.rstrip('/')}/images/{img_id}"
                
                # Test without following redirects
                r1 = await no_redir_client.get(url)
                print(f"[{title}] ID {img_id}: no_redir status={r1.status_code}, loc={r1.headers.get('location')}")
                
                # If 302, test with following redirects
                if r1.status_code == 302:
                    r2 = await redir_client.get(url)
                    print(f"    -> with follow_redirects: status={r2.status_code}, len={len(r2.content)}, type={r2.headers.get('content-type')}")

asyncio.run(test())
