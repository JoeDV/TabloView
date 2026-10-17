from tablo_api import TabloClient
from app.tablo_client import tablo_manager

tablo_manager.load_cached_config()
client = TabloClient(tablo_manager.device)

all_ch = client.channels(include_ott=True)
ott_channels = [c for c in all_ch if c.kind == 'ott']
print(f"Total FAST streaming channels: {len(ott_channels)}")
if ott_channels:
    sample = ott_channels[0]
    print(f"Testing FAST channel: {sample.call_sign} (ID: {sample.identifier})")
    try:
        stream = client.watch(sample)
        print("Success! FAST Playlist URL:", stream.playlist_url)
    except Exception as e:
        print("FAST Tune error:", e)
