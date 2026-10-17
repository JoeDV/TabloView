import sys, os, time
sys.path.insert(0, os.path.abspath('.'))
import asyncio
from app.tablo_client import tablo_manager

async def test():
    t0 = time.time()
    res = await tablo_manager.request_local("GET", "/guide/airings")
    paths = res.json()
    print(f"Total: {len(paths)}")
    
    t1 = time.time()
    sem = asyncio.Semaphore(60)
    async def fetch(p):
        async with sem:
            try:
                r = await tablo_manager.request_local("GET", p)
                if r.status_code == 200: return r.json()
            except Exception: pass
            return None

    results = await asyncio.gather(*[fetch(p) for p in paths[:1000]])
    valid = [r for r in results if r]
    print(f"Fetched {len(valid)} airings in {time.time()-t1:.2f}s")

asyncio.run(test())
