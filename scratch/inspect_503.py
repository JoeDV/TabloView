import json
import requests
from tablo_api import TabloAuth, TabloClient
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()
dev = tablo_manager.device
client = TabloClient(dev)

ota = client.channels(include_ott=False)
ch = ota[0] # WTTVDT1 CBS
path = f"/guide/channels/{ch.identifier}/watch"

body = json.dumps({
    "bandwidth": None,
    "extra": {
        "limitedAdTracking": 1,
        "deviceOSVersion": "16.6",
        "lang": "en_US",
        "height": 1080,
        "deviceId": "00000000-0000-0000-0000-000000000000",
        "width": 1920,
        "deviceModel": "iPhone10,1",
        "deviceMake": "Apple",
        "deviceOS": "iOS",
    },
    "device_id": dev.client_id,
    "platform": "ios",
})

auth_header, date_header = TabloAuth.make_device_auth("POST", path, body)

resp = requests.post(
    dev.local_url.rstrip("/") + path,
    data=body.encode(),
    params="lh",
    headers={
        "Authorization": auth_header,
        "Date": date_header,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "User-Agent": "Tablo-FAST/1.7.0 (Mobile; iPhone; iOS 18.4)",
    },
    timeout=15,
)

print("Status code:", resp.status_code)
print("Headers:", dict(resp.headers))
print("Response text:", resp.text)
