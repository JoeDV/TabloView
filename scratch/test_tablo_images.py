import asyncio
import httpx
from app.tablo_client import tablo_manager

async def main():
    tablo_manager.load_cached_config()
    dev = tablo_manager.device
    print("Device:", dev.name, "local_url:", dev.local_url)
    
    test_ids = [
        "292920", # 9-1-1 cover
        "48281",  # 9-1-1 backdrop
        "292919", # 9-1-1 thumbnail
        "25830",  # working image
        "13199",  # 48 hours cover
    ]
    
    for img_id in test_ids:
        url = f"{dev.local_url.rstrip('/')}/images/{img_id}"
        r = await tablo_manager._http.get(url)
        loc = r.headers.get("location")
        print(f"ID {img_id}: 302 Location: {loc}")
        if loc:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                try:
                    r2 = await client.get(loc, timeout=6)
                    print(f"   -> Result: HTTP {r2.status_code}, len={len(r2.content)}, type={r2.headers.get('content-type')}")
                except Exception as e:
                    print(f"   -> Fetch error: {e}")

asyncio.run(main())
