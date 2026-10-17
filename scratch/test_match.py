import sys
sys.path.insert(0, '.')
from app.database import get_epg_schedule

epg = get_epg_schedule(hours=6)
print("Airings by call sign keys:", list(epg["airings_by_channel"].keys()))
ota_channels = [
    {"call_sign": "WTTV", "name": "4.1 WTTV"},
    {"call_sign": "WRTV", "name": "6.1 WRTV"},
    {"call_sign": "WTHR", "name": "13.1 WTHR"},
    {"call_sign": "WFYI", "name": "20.1 WFYI"},
    {"call_sign": "WTTK", "name": "29.1 WTTK"},
    {"call_sign": "WXIN", "name": "59.1 WXIN"},
    {"call_sign": "WDTI", "name": "69.1 WDTI"}
]

for ch in ota_channels:
    cs = ch["call_sign"]
    clean = cs.replace("-HD", "").replace("DT1", "").strip()
    airings = epg["airings_by_channel"].get(cs) or epg["airings_by_channel"].get(clean) or epg["airings_by_channel"].get(f"{clean}-1")
    if not airings and clean == "WDTI":
        airings = epg["airings_by_channel"].get("DYSTR")
    print(f"Matched {ch['name']} ({cs}) -> {len(airings) if airings else 0} airings")
