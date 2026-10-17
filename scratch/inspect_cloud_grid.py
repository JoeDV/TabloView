import sys
sys.path.insert(0, '.')
import requests
from app.tablo_client import tablo_manager
import tablo_api.client as tc

dev = tablo_manager.device
headers = {
    "Authorization": f"Bearer {dev.account_token}",
    "Lighthouse": dev.lighthouse_token,
    "Accept": "*/*",
    "User-Agent": tc._CLOUD_USER_AGENT,
    "Content-Type": "application/json",
}

for limit in [10, 25, 50, 100, 200]:
    url = f"{tc._CLOUD_HOST}/api/v2/account/{dev.lighthouse_token}/guide/grid/?limit={limit}"
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    grid = data.get("grid", [])
    print(f"limit={limit} -> Status: {r.status_code}, Returned channels: {len(grid)}, next: {bool(data.get('next'))}")
