"""Tablo 4th Gen Connection & API Discovery CLI Script

Verifies login against LighthouseTV cloud authentication, discovers local Tablo DVR(s),
tests HMAC-MD5 signed device requests, and probes library/recording endpoints.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
load_dotenv()

from tablo_api import TabloAuth
from tablo_api.models import TabloDevice

DEBUG_DIR = Path("debug_data")
DEBUG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = Path("data/config.json")


def save_debug(filename: str, data: any):
    """Save data as pretty JSON in debug_data directory."""
    filepath = DEBUG_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [Saved] -> {filepath}")


def request_local_device(device: TabloDevice, method: str, path: str, body: str = "") -> requests.Response:
    """Send an HMAC-MD5 signed request to the local Tablo 4th Gen device."""
    auth_header, date_header = TabloAuth.make_device_auth(method, path, body)
    url = device.local_url.rstrip("/") + path
    headers = {
        "Authorization": auth_header,
        "Date": date_header,
        "User-Agent": "Tablo-FAST/1.7.0 (Mobile; iPhone; iOS 18.4)",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    if body:
        headers["Content-Type"] = "application/json"
    
    # Device might need 'lh' query param
    return requests.request(method, url, data=body.encode() if body else None, headers=headers, timeout=12)


def main():
    print("=" * 65)
    print("  Tablo 4th Gen Connection & Recordings Discovery")
    print("=" * 65)

    # 1. Credentials resolution
    email = os.getenv("TABLO_EMAIL")
    password = os.getenv("TABLO_PASSWORD")

    if not email or not password:
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                email = cfg.get("email")
                password = cfg.get("password")
            except Exception:
                pass

    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]

    if not email or not password:
        print("\n[!] No Tablo credentials found in .env or data/config.json.")
        print("Usage:")
        print("  python test_connection.py <email> <password>")
        print("Or create a .env file with:")
        print("  TABLO_EMAIL=your_email")
        print("  TABLO_PASSWORD=your_password\n")
        try:
            email = input("Enter Tablo Email: ").strip()
            password = input("Enter Tablo Password: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(1)

    if not email or not password:
        print("[Error] Email and password are required.")
        sys.exit(1)

    print(f"\n[1] Authenticating with Lighthouse Cloud ({email})...")
    try:
        auth = TabloAuth(email, password)
        devices: list[TabloDevice] = auth.discover()
    except Exception as e:
        print(f"[ERROR] Cloud authentication or discovery failed: {e}")
        sys.exit(1)

    if not devices:
        print("[ERROR] No Tablo devices found on this account.")
        sys.exit(1)

    print(f"[✓] Successfully authenticated! Discovered {len(devices)} device(s):")
    for idx, dev in enumerate(devices):
        print(f"    #{idx + 1}: Name: {dev.name} | SID: {dev.sid} | Local URL: {dev.local_url}")

    # Use first device by default
    active_device = devices[0]
    print(f"\n[2] Selecting Active Device: {active_device.name} ({active_device.local_url})")

    # Save credentials and device cache locally
    CONFIG_FILE.parent.mkdir(exist_ok=True, parents=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "email": email,
            "password": password,
            "device": active_device.model_dump(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)
    print(f"[✓] Saved cached device config to {CONFIG_FILE}")

    # Also update/create .env if not already present
    env_file = Path(".env")
    if not env_file.exists():
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"TABLO_EMAIL={email}\nTABLO_PASSWORD={password}\nPORT=7070\n")
        print(f"[✓] Created .env with credentials")

    # 3. Test unauthenticated /ping
    print("\n[3] Testing unauthenticated /ping...")
    try:
        ping_resp = requests.get(active_device.local_url.rstrip("/") + "/ping", timeout=5)
        print(f"    Ping status: {ping_resp.status_code} | Body: {ping_resp.text}")
    except Exception as e:
        print(f"    [WARNING] /ping failed: {e}")

    # 4. Probing signed endpoints
    print("\n[4] Probing signed local Tablo endpoints...")

    endpoints = [
        ("GET", "/server/info", "server_info.json"),
        ("GET", "/server/harddrives", "server_harddrives.json"),
        ("GET", "/recordings/airings", "recordings_airings.json"),
        ("GET", "/recordings/series", "recordings_series.json"),
        ("GET", "/recordings/shows", "recordings_shows.json"),
        ("GET", "/recordings/movies", "recordings_movies.json"),
        ("GET", "/recordings/sports", "recordings_sports.json"),
        ("GET", "/guide/channels", "guide_channels.json"),
    ]

    probe_results = {}
    airing_paths = []
    series_paths = []

    for method, path, save_file in endpoints:
        try:
            resp = request_local_device(active_device, method, path)
            status = resp.status_code
            print(f"    {method} {path:<26} -> {status}", end="")
            if resp.ok:
                data = resp.json()
                count = len(data) if isinstance(data, list) else len(data.keys())
                print(f" ({count} items)")
                save_debug(save_file, data)
                probe_results[path] = {"status": status, "count": count, "success": True}
                if path == "/recordings/airings" and isinstance(data, list):
                    airing_paths = data
                elif path == "/recordings/series" and isinstance(data, list):
                    series_paths = data
            else:
                print(f" (Error: {resp.text[:60]})")
                probe_results[path] = {"status": status, "error": resp.text[:100], "success": False}
        except Exception as e:
            print(f"    {method} {path:<26} -> EXCEPTION: {e}")
            probe_results[path] = {"error": str(e), "success": False}

    # 5. Inspect individual recording / airing details
    if airing_paths:
        sample_paths = airing_paths[:5]
        print(f"\n[5] Probing first {len(sample_paths)} airing details from /recordings/airings...")
        sample_airings = []
        for p in sample_paths:
            try:
                r = request_local_device(active_device, "GET", p)
                if r.ok:
                    airing_data = r.json()
                    sample_airings.append(airing_data)
                    ad = airing_data.get("airing_details", {})
                    ep = airing_data.get("episode", {})
                    show_title = ad.get("show_title") or ep.get("show_title") or airing_data.get("series", {}).get("title")
                    ep_title = ep.get("title") or ""
                    season = ep.get("season_number")
                    episode_num = ep.get("episode_number")
                    print(f"    Airing {p}: {show_title} - S{season}E{episode_num}: {ep_title}")
                else:
                    print(f"    Airing {p} -> HTTP {r.status_code}")
            except Exception as e:
                print(f"    Airing {p} -> Exception: {e}")
        if sample_airings:
            save_debug("sample_airings_detailed.json", sample_airings)

            # Test watch endpoint for the first airing
            first_airing_path = sample_paths[0]
            print(f"\n[6] Testing watch endpoint for sample airing ({first_airing_path})...")
            
            # Try POST /<airing_path>/watch
            watch_path = f"{first_airing_path}/watch"
            watch_body = json.dumps({
                "device_id": active_device.client_id,
                "platform": "ios"
            })
            try:
                watch_resp = request_local_device(active_device, "POST", watch_path, watch_body)
                print(f"    POST {watch_path} -> HTTP {watch_resp.status_code}")
                if watch_resp.ok:
                    watch_data = watch_resp.json()
                    print(f"    [SUCCESS] Playlist URL: {watch_data.get('playlist_url')}")
                    save_debug("sample_watch_response.json", watch_data)
                else:
                    print(f"    Watch response text: {watch_resp.text}")
                    # Also try watch without body
                    watch_resp2 = request_local_device(active_device, "POST", watch_path, "")
                    print(f"    POST {watch_path} (no body) -> HTTP {watch_resp2.status_code}: {watch_resp2.text[:100]}")
            except Exception as e:
                print(f"    Watch probe exception: {e}")

    # 6. Inspect series details
    if series_paths:
        print(f"\n[7] Probing first {min(3, len(series_paths))} series details from /recordings/series...")
        sample_series = []
        for sp in series_paths[:3]:
            try:
                sr = request_local_device(active_device, "GET", sp)
                if sr.ok:
                    s_data = sr.json()
                    sample_series.append(s_data)
                    print(f"    Series {sp}: {s_data.get('series', {}).get('title')} ({s_data.get('series', {}).get('episodes_count', 0)} eps)")
            except Exception as e:
                print(f"    Series {sp} exception: {e}")
        if sample_series:
            save_debug("sample_series_detailed.json", sample_series)

    # 7. Cloud Proxy Probe
    print("\n[8] Probing Lighthouse Cloud Guide / DVR proxy...")
    cloud_url = f"https://lighthousetv.ewscloud.com/api/v2/account/{active_device.lighthouse_token}/guide/channels/"
    try:
        c_resp = requests.get(
            cloud_url,
            headers={
                "Authorization": f"Bearer {active_device.account_token}",
                "Lighthouse": active_device.lighthouse_token,
                "User-Agent": "Tablo-FAST/2.0.0 (Mobile; iPhone; iOS 16.6)",
                "Accept": "*/*",
            },
            timeout=10
        )
        print(f"    GET cloud channels -> HTTP {c_resp.status_code} ({len(c_resp.json()) if c_resp.ok else 0} channels)")
        if c_resp.ok:
            save_debug("cloud_channels.json", c_resp.json()[:10])
    except Exception as e:
        print(f"    Cloud probe exception: {e}")

    print("\n" + "=" * 65)
    print("  Discovery Complete! All debug data captured in ./debug_data/")
    print("=" * 65)


if __name__ == "__main__":
    main()
