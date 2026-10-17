import urllib.request
import json

url = 'http://localhost:7070/api/live/epg?hours=4'
resp = urllib.request.urlopen(url)
data = json.loads(resp.read())

print("Status: 200 OK")
print(f"Window: {data['window_start']} to {data['window_end']}")
print(f"Time Slots ({len(data['slots'])}): {[s['time_str'] for s in data['slots']]}")
print(f"Total Channels: {data['count']}")

ota = [c for c in data['channels'] if c['kind'] == 'ota']
print(f"OTA Channels ({len(ota)}):")
for c in ota:
    print(f"\n  Channel: {c['name']} ({c['network'] or 'OTA'}) | Logo: {'Yes' if c['logo_url'] else 'Fallback'}")
    for a in c['airings'][:4]:
        dur = a['duration'] // 60
        new_tag = " [NEW]" if a['is_new'] else ""
        print(f"     [{a['air_datetime']}] ({dur}m){new_tag} {a['title']} - {a['episode_title'] or 'Broadcast'}")
