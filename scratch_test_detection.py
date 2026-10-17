import sys, os, time
sys.path.insert(0, os.path.abspath('.'))
import asyncio
from app.tablo_client import tablo_manager

async def test():
    res = await tablo_manager.request_local("GET", "/guide/airings")
    paths = res.json()
    
    sem = asyncio.Semaphore(60)
    async def fetch(p):
        async with sem:
            try:
                r = await tablo_manager.request_local("GET", p)
                if r.status_code == 200: return r.json()
            except Exception: pass
            return None

    results = await asyncio.gather(*[fetch(p) for p in paths[:1500]])
    airings = [r for r in results if r]
    
    primetime_shows = set()
    premiere_shows = set()
    
    for a in airings:
        qual = [q.lower() for q in a.get('qualifiers', [])]
        ep = a.get('episode', {})
        ad = a.get('airing_details', {})
        show_title = ad.get('show_title') or 'Unknown'
        ep_num = ep.get('number') or ep.get('episode_number') or 0
        season_num = ep.get('season_number') or 0
        
        is_new = 'new' in qual
        is_prime = 'primetime' in qual
        is_prem = any(p in qual for p in ['season_premiere', 'series_premiere', 'premiere']) or (is_new and ep_num == 1 and season_num > 0)
        
        if is_new and is_prime:
            primetime_shows.add(f"{show_title} (S{season_num}E{ep_num}) - {ad.get('datetime')}")
        if is_prem:
            premiere_shows.add(f"{show_title} (S{season_num}E{ep_num}) - {qual} - {ad.get('datetime')}")
            
    print(f"\nFound {len(primetime_shows)} Primetime New episodes (in first 1500 airings):")
    for s in sorted(list(primetime_shows))[:15]:
        print("  ", s)
        
    print(f"\nFound {len(premiere_shows)} Season/Series Premieres:")
    for s in sorted(list(premiere_shows))[:15]:
        print("  ", s)

asyncio.run(test())
