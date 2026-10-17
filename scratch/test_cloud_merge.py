import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
import requests
from app.tablo_client import tablo_manager
from app.database import get_epg_schedule
import tablo_api.client as tc

dev = tablo_manager.device
epg = get_epg_schedule(hours=6)
window_start = datetime.fromisoformat(epg["window_start"].replace("Z", "+00:00"))
window_end = datetime.fromisoformat(epg["window_end"].replace("Z", "+00:00"))

print(f"Window: {window_start} to {window_end}")

# Fetch cloud grid
url = f"{tc._CLOUD_HOST}/api/v2/account/{dev.lighthouse_token}/guide/grid/?day={window_start.strftime('%Y-%m-%d')}&limit=200"
headers = {
    "Authorization": f"Bearer {dev.account_token}",
    "Lighthouse": dev.lighthouse_token,
    "User-Agent": tc._CLOUD_USER_AGENT
}
r = requests.get(url, headers=headers, timeout=15)
cloud_grid = r.json().get("grid", [])

fast_with_airings = 0
for item in cloud_grid:
    ch = item.get("channel", {})
    if ch.get("kind") != "ott":
        continue
    matching = []
    for a in item.get("airings", []):
        try:
            a_start = datetime.fromisoformat(a["datetime"].replace("Z", "+00:00"))
            a_end = a_start + timedelta(seconds=a["duration"])
            if a_end > window_start and a_start < window_end:
                matching.append(a)
        except Exception:
            pass
    if matching:
        fast_with_airings += 1

print(f"FAST channels in cloud: {sum(1 for i in cloud_grid if i.get('channel',{}).get('kind') == 'ott')}")
print(f"FAST channels with matching window airings: {fast_with_airings}")

sample_item = next(i for i in cloud_grid if "Action Plus" in i.get("channel",{}).get("name",""))
print("\nAction Plus matching window airings:")
for a in sample_item.get("airings", []):
    a_start = datetime.fromisoformat(a["datetime"].replace("Z", "+00:00"))
    a_end = a_start + timedelta(seconds=a["duration"])
    if a_end > window_start and a_start < window_end:
        title = (a.get("show") or {}).get("title") or a.get("title")
        print(f"   [{a['datetime']}] ({a['duration']//60}m) {title} - {a.get('title')}")
