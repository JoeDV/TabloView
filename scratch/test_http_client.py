import asyncio
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()

async def test():
    url = f"{tablo_manager.device.local_url.rstrip('/')}/images/292920"
    resp = await tablo_manager._http.get(url, timeout=6)
    print("status_code:", resp.status_code)
    print("history:", [h.status_code for h in resp.history])
    print("url:", resp.url)
    print("content length:", len(resp.content))

asyncio.run(test())
