import sys
sys.path.insert(0, '.')
import json
import requests
from app.tablo_client import tablo_manager
import tablo_api.client as tc

dev = tablo_manager.device
path = f"/api/v2/account/{dev.lighthouse_token}/guide/channels/"
url = f"{tc._CLOUD_HOST}{path}"

resp = requests.get(
    url,
    headers={
        "Authorization": f"Bearer {dev.account_token}",
        "Lighthouse": dev.lighthouse_token,
        "Accept": "*/*",
        "User-Agent": tc._CLOUD_USER_AGENT,
        "Content-Type": "application/json",
    },
    timeout=10
)

print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Number of channels in cloud: {len(data)}")

# Let's inspect OTT/FAST channels specifically
ott_channels = [c for c in data if c.get("kind") == "ott"]
print(f"Number of OTT/FAST channels: {len(ott_channels)}")
if ott_channels:
    print("Sample OTT raw channel:")
    print(json.dumps(ott_channels[0], indent=2))
    print("Sample OTT 2:")
    print(json.dumps(ott_channels[1], indent=2))
