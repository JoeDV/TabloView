import json
from tablo_api import TabloClient
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()
dev = tablo_manager.device
print("Device:", dev.name, "SID:", dev.sid, "local_url:", dev.local_url)

client = TabloClient(dev)

print("\n--- Fetching Channels ---")
try:
    channels = client.channels(include_ott=False) # OTA only
    print(f"Found {len(channels)} OTA channels:")
    for ch in channels[:10]:
        print(f"  {ch.major}.{ch.minor} {ch.call_sign} ({ch.network}) -> ID: {ch.identifier}")
except Exception as e:
    print("Error fetching channels:", e)
