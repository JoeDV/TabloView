import sys
sys.path.insert(0, '.')
import requests
from app.tablo_client import tablo_manager
import tablo_api.client as tc

dev = tablo_manager.device
r = requests.get(
    f"{tc._CLOUD_HOST}/api/v2/account/{dev.lighthouse_token}/guide/grid/?day=2026-10-16&limit=200",
    headers={
        "Authorization": f"Bearer {dev.account_token}",
        "Lighthouse": dev.lighthouse_token,
        "User-Agent": tc._CLOUD_USER_AGENT
    },
    timeout=15
)
grid = r.json().get("grid", [])

target_names = ["ACCUWEATHER", "ACTIONPLUS", "ALLBLKGEMS", "ALLREALITY", "ALLWEDDINGS", "AMCESPANOL"]

for item in grid:
    ch = item.get("channel", {})
    name = ch.get("name", "").upper()
    call = (ch.get("ott") or {}).get("callSign", "").upper()
    if any(t in name or t in call for t in target_names):
        print(f"\nChannel: {ch.get('name')} | ID: {ch.get('identifier')} | Airings count: {len(item.get('airings', []))}")
        for a in item.get("airings", [])[:4]:
            title = a.get("show", {}).get("title") if a.get("show") else a.get("title")
            ep = a.get("title") if a.get("show") else a.get("episode_title")
            print(f"   [{a.get('datetime')}] ({a.get('duration')}s) {title} - {ep}")
