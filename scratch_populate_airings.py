import sys, os, time
sys.path.insert(0, os.path.abspath('.'))
import asyncio, sqlite3, json
from app.tablo_client import tablo_manager
from app.database import init_db, get_connection

async def populate():
    t0 = time.time()
    
    # 1. Ensure table exists
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guide_airings (
                path TEXT PRIMARY KEY,
                series_path TEXT,
                show_title TEXT NOT NULL,
                episode_title TEXT,
                season_number INTEGER DEFAULT 0,
                episode_number INTEGER DEFAULT 0,
                air_datetime TEXT,
                duration INTEGER DEFAULT 0,
                channel_call_sign TEXT,
                channel_network TEXT,
                qualifiers TEXT,
                is_new INTEGER DEFAULT 0,
                is_primetime INTEGER DEFAULT 0,
                is_premiere INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ga_series_path ON guide_airings(series_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ga_air_datetime ON guide_airings(air_datetime)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ga_primetime_new ON guide_airings(is_new, is_primetime)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ga_premiere ON guide_airings(is_premiere)")
        conn.commit()

    # 2. Fetch airings list
    res = await tablo_manager.request_local("GET", "/guide/airings")
    if res.status_code != 200:
        print(f"Failed to fetch airings: {res.status_code}")
        return
    paths = res.json()
    print(f"Fetched {len(paths)} airing paths from Tablo in {time.time()-t0:.2f}s")

    # 3. Concurrently fetch all airings
    sem = asyncio.Semaphore(50)
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    
    async def fetch_airing(p):
        async with sem:
            try:
                r = await tablo_manager.request_local("GET", p)
                if r.status_code == 200:
                    d = r.json()
                    ep = d.get('episode', {})
                    ad = d.get('airing_details', {})
                    ch = ad.get('channel', {}).get('channel', {})
                    qual = [q.lower() for q in d.get('qualifiers', [])]
                    ep_num = ep.get('number') or ep.get('episode_number') or 0
                    season_num = ep.get('season_number') or 0
                    
                    is_new = 1 if 'new' in qual else 0
                    is_primetime = 1 if 'primetime' in qual else 0
                    is_premiere = 1 if (
                        'season_premiere' in qual or 
                        'series_premiere' in qual or 
                        ('premiere' in qual and is_new) or 
                        (is_new and ep_num == 1 and season_num > 0)
                    ) else 0

                    ep_title = ep.get('title')
                    if not ep_title:
                        ep_title = f"Episode {ep_num}" if ep_num else (ad.get('show_title') or "Episode")

                    return (
                        p,
                        d.get('series_path') or '',
                        ad.get('show_title') or 'Unknown',
                        ep_title,
                        season_num,
                        ep_num,
                        ad.get('datetime') or '',
                        ad.get('duration') or 0,
                        ch.get('call_sign') or ch.get('name') or '',
                        ch.get('network') or '',
                        json.dumps(qual),
                        is_new,
                        is_primetime,
                        is_premiere,
                        now_iso
                    )
            except Exception:
                pass
            return None

    t1 = time.time()
    results = await asyncio.gather(*[fetch_airing(p) for p in paths])
    valid_rows = [r for r in results if r]
    print(f"Downloaded {len(valid_rows)} detailed airings in {time.time()-t1:.2f}s")

    # 4. Insert into database
    with get_connection() as conn:
        conn.executemany("""
            INSERT INTO guide_airings (
                path, series_path, show_title, episode_title, season_number, episode_number,
                air_datetime, duration, channel_call_sign, channel_network, qualifiers,
                is_new, is_primetime, is_premiere, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                series_path = excluded.series_path,
                show_title = excluded.show_title,
                episode_title = excluded.episode_title,
                season_number = excluded.season_number,
                episode_number = excluded.episode_number,
                air_datetime = excluded.air_datetime,
                duration = excluded.duration,
                channel_call_sign = excluded.channel_call_sign,
                channel_network = excluded.channel_network,
                qualifiers = excluded.qualifiers,
                is_new = excluded.is_new,
                is_primetime = excluded.is_primetime,
                is_premiere = excluded.is_premiere,
                updated_at = excluded.updated_at
        """, valid_rows)
        conn.commit()

    print(f"Successfully saved {len(valid_rows)} airings to SQLite in {time.time()-t0:.2f}s total!")

    # Verify counts
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT series_path) FROM guide_airings WHERE is_new = 1 AND is_primetime = 1")
        print("Shows with Primetime New:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(DISTINCT series_path) FROM guide_airings WHERE is_premiere = 1")
        print("Shows with Season/Series Premieres:", cur.fetchone()[0])

asyncio.run(populate())
