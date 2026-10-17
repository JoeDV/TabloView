import json
import requests
from tablo_api import TabloAuth
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()
dev = tablo_manager.device

ch_id = "S35595_004_01" # WTTV 4.1 CBS
path = f"/guide/channels/{ch_id}/watch"

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

print("Tune response:", resp.status_code, resp.text)
if resp.status_code == 200:
    data = resp.json()
    token = data.get("token")
    playlist_url = data.get("playlist_url")
    print(f"Token: {token}")
    print(f"Playlist: {playlist_url}")
    
    # Check if there is a stop or delete endpoint for token
    for test_path, method in [
        (f"/guide/channels/{ch_id}/watch", "DELETE"),
        (f"/stream/{token}", "DELETE"),
        (f"/stream/token/{token}", "DELETE"),
        (f"/guide/channels/{ch_id}/watch/stop", "POST"),
        (f"/server/tuners", "GET")
    ]:
        try:
            ah, dh = TabloAuth.make_device_auth(method, test_path)
            r = requests.request(
                method,
                dev.local_url.rstrip("/") + test_path,
                headers={"Authorization": ah, "Date": dh, "User-Agent": "Tablo-FAST/1.7.0 (Mobile; iPhone; iOS 18.4)"},
                timeout=5
            )
            print(f"Test {method} {test_path} -> HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"Test {method} {test_path} -> Error: {e}")
