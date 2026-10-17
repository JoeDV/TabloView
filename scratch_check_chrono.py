import sys, os
sys.path.insert(0, os.path.abspath('.'))
import asyncio
from app.tablo_client import tablo_manager

async def test():
    res = await tablo_manager.request_local("GET", "/guide/airings")
    paths = res.json()
    print(f"Total: {len(paths)}")
    
    sem = asyncio.Semaphore(25)
    async def get_info(p):
        async with sem:
            try:
                r = await tablo_manager.request_local("GET", p)
                if r.status_code == 200:
                    d = r.json()
                    ad = d.get('airing_details', {})
                    return (p, ad.get('datetime'), ad.get('show_title'), d.get('qualifiers'))
            except Exception:
                pass
            return None

    results = await asyncio.gather(*[get_info(p) for p in paths[:50]])
    for r in results:
        if r:
            print(f"{r[1]} | {r[2]} | {r[3]}")

asyncio.run(test())
