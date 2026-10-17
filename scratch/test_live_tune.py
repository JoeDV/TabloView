import json
from tablo_api import TabloClient
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()
dev = tablo_manager.device
client = TabloClient(dev)

ota = client.channels(include_ott=False)
print("Testing live tuning on:", ota[0].call_sign, ota[0].network, ota[0].identifier)

try:
    stream = client.watch(ota[0])
    print("Success! Stream details:")
    print("  Playlist URL:", stream.playlist_url)
    print("  Token:", stream.token)
    print("  Expires:", stream.expires)
    print("  Keepalive:", stream.keepalive)
except Exception as e:
    print("Live tune error:", type(e), e)
