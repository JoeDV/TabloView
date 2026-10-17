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

base = f"{tc._CLOUD_HOST}/api/v2/account/{dev.lighthouse_token}/guide"

test_paths = [
    f"{base}/channels/S999050432_522_29/",
    f"{base}/channels/S999050432_522_29/airings/",
    f"{base}/channels/S999050432_522_29/schedule/",
    f"{base}/channels/S999050432_522_29/programs/",
    f"{base}/airings/",
    f"{base}/programs/",
    f"{base}/schedule/",
    f"{base}/epg/",
    f"{base}/grid/",
    f"{tc._CLOUD_HOST}/api/v2/guide/channels/S999050432_522_29/",
    f"{tc._CLOUD_HOST}/api/v2/guide/channels/S999050432_522_29/airings/",
]

for p in test_paths:
    try:
        r = requests.get(p, headers=headers, timeout=5)
        print(f"[{r.status_code}] {p}")
        if r.status_code == 200:
            print("  Response preview:", r.text[:200])
    except Exception as e:
        print(f"[ERR] {p} -> {e}")
