import asyncio
from app.tablo_client import tablo_manager

async def main():
    r = await tablo_manager.request_local('GET', '/guide/series/episodes/273073')
    print("Episode 273073 details:")
    print(r.json())

asyncio.run(main())
