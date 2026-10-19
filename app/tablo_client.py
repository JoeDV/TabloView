"""Tablo 4th Gen client manager, handling cloud auth, token caching,
and HMAC-MD5 signed requests to the local Tablo hardware.
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import httpx

from tablo_api import TabloAuth, TabloClient
from tablo_api.models import TabloDevice
from .config import CONFIG_FILE, TABLO_EMAIL, TABLO_PASSWORD

# Requests in flight to the Tablo at once. Its small web server stops accepting connections for a
# minute or more when a sync fires dozens in parallel, so everything shares this limit.
LOCAL_CONCURRENCY = 4
# Of those, at most this many for syncs (request_bulk), so what the user clicks never waits long
BULK_CONCURRENCY = 2


class TabloManager:
    def __init__(self):
        self.device: Optional[TabloDevice] = None
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.devices: List[TabloDevice] = []
        self._http = httpx.AsyncClient(timeout=30, follow_redirects=True)
        # Sign-in problems seen recently, by source ("device" = local Tablo, "cloud" = Tablo account);
        # cleared again as soon as a request from that source succeeds
        self.auth_problems: Dict[str, str] = {}
        # When requests to the Tablo started failing to connect (None while it answers)
        self.unreachable_since: Optional[float] = None
        self._local_slots = asyncio.Semaphore(LOCAL_CONCURRENCY)
        self._bulk_slots = asyncio.Semaphore(BULK_CONCURRENCY)
        self.load_cached_config()

    UNREACHABLE_MESSAGE = "Your Tablo isn't responding right now. This usually clears up on its own: wait a minute and try again."

    @property
    def tablo_unreachable(self) -> bool:
        return self.unreachable_since is not None

    AUTH_MESSAGES = {
        "device": "Your Tablo stopped accepting TabloView's access.",
        "cloud": "Your Tablo account sign-in has expired.",
    }

    def note_auth(self, source: str, ok: bool):
        if ok:
            self.auth_problems.pop(source, None)
        elif source not in self.auth_problems:
            self.auth_problems[source] = self.AUTH_MESSAGES[source]
            print(f"[TabloManager] Sign-in problem ({source}): {self.auth_problems[source]}")

    @property
    def auth_problem(self) -> Optional[str]:
        return next(iter(self.auth_problems.values()), None)

    def load_cached_config(self):
        """Load credentials and device info from config file or env."""
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.email = data.get("email")
                if "device" in data and data["device"]:
                    self.device = TabloDevice.model_validate(data["device"])
                if "devices" in data and data["devices"]:
                    self.devices = [TabloDevice.model_validate(d) for d in data["devices"]]
                # Older configs stored the plaintext password; scrub it
                if "password" in data:
                    self.save_config()
            except Exception as e:
                print(f"[TabloManager] Error loading config: {e}")

        if not self.email and TABLO_EMAIL:
            self.email = TABLO_EMAIL
            self.password = TABLO_PASSWORD

    def save_config(self):
        """Save credentials and discovered device data."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            # Password is deliberately not persisted; device tokens are all that's needed
            "email": self.email,
            "device": self.device.model_dump() if self.device else None,
            "devices": [d.model_dump() for d in self.devices],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    async def login(self, email: str, password: str) -> List[TabloDevice]:
        """Authenticate with Lighthouse cloud and discover local devices."""
        auth = TabloAuth(email, password)
        # TabloAuth.discover() is synchronous, run in executor
        loop = asyncio.get_event_loop()
        devices: List[TabloDevice] = await loop.run_in_executor(None, auth.discover)

        if not devices:
            raise ValueError("No Tablo devices found on this account.")

        self.email = email
        self.password = password
        self.devices = devices
        self.device = devices[0]
        self.save_config()
        self.auth_problems.clear()
        return devices

    def select_device(self, sid: str) -> TabloDevice:
        for d in self.devices:
            if d.sid == sid:
                self.device = d
                self.save_config()
                self.auth_problems.clear()
                return d
        raise ValueError(f"Device with SID '{sid}' not found")

    def logout(self):
        self.auth_problems.clear()
        self.device = None
        self.devices = []
        self.email = None
        self.password = None
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    @property
    def is_authenticated(self) -> bool:
        return self.device is not None

    async def request_bulk(self, method: str, path: str, body: str = "") -> httpx.Response:
        """request_local for syncs: they queue among themselves first, so an interactive request
        waits behind at most BULK_CONCURRENCY of them rather than the whole sync."""
        async with self._bulk_slots:
            return await self.request_local(method, path, body)

    async def request_local(self, method: str, path: str, body: str = "") -> httpx.Response:
        """Send an HMAC-MD5 authenticated request to the active local Tablo device."""
        if not self.device:
            raise RuntimeError("Tablo device not configured or authenticated")

        url = self.device.local_url.rstrip("/") + path
        try:
            async with self._local_slots:
                # Signed once a slot is free, so the signature's date isn't stale after waiting.
                # The Tablo signs only the bare path: a query string (e.g. ?state=scheduled) must be
                # left out of the signature or the device answers 401.
                auth_header, date_header = TabloAuth.make_device_auth(method, path.split("?", 1)[0], body)
                headers = {
                    "Authorization": auth_header,
                    "Date": date_header,
                    "User-Agent": "Tablo-FAST/1.7.0 (Mobile; iPhone; iOS 18.4)",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                }
                if body:
                    headers["Content-Type"] = "application/json"
                resp = await self._http.request(
                    method=method,
                    url=url,
                    content=body.encode() if body else None,
                    headers=headers
                )
        except httpx.TransportError:
            # Connection refused or timed out: the Tablo sometimes stops answering for a minute or so
            if self.unreachable_since is None:
                self.unreachable_since = time.time()
                print("[TabloManager] Tablo isn't responding")
            raise
        if self.unreachable_since is not None:
            print(f"[TabloManager] Tablo is responding again (after {time.time() - self.unreachable_since:.0f} s)")
            self.unreachable_since = None
        if resp.status_code == 401:
            self.note_auth("device", ok=False)
        elif resp.status_code < 400:
            self.note_auth("device", ok=True)
        return resp

    async def get_storage_info(self) -> Dict[str, Any]:
        """Fetch hard drive usage and capacity from /server/harddrives."""
        if not self.device:
            return {"connected": False, "drives": []}

        try:
            resp = await self.request_local("GET", "/server/harddrives")
            if resp.status_code == 200:
                drives_data = resp.json()
                # Parse drives
                drives = []
                total_bytes = 0
                used_bytes = 0

                drive_list = drives_data if isinstance(drives_data, list) else [drives_data]
                for d in drive_list:
                    # In Tablo 4th gen: keys are size, usage, free
                    cap = d.get("size") or d.get("capacity") or d.get("total_bytes") or 0
                    used = d.get("usage") or d.get("used") or d.get("used_bytes") or 0
                    if cap == 0 and "free" in d:
                        cap = used + d["free"]
                    free = d.get("free") or (cap - used if cap >= used else 0)

                    total_bytes += cap
                    used_bytes += used
                    drives.append({
                        "name": d.get("name", "Tablo Drive"),
                        "total_gb": round(cap / (1024**3), 1),
                        "used_gb": round(used / (1024**3), 1),
                        "free_gb": round(free / (1024**3), 1),
                        "percent_used": round((used / cap * 100), 1) if cap > 0 else 0
                    })

                total_gb = round(total_bytes / (1024**3), 1)
                used_gb = round(used_bytes / (1024**3), 1)
                free_gb = round((total_bytes - used_bytes) / (1024**3), 1)
                pct = round((used_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0

                return {
                    "connected": True,
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "free_gb": free_gb,
                    "percent_used": pct,
                    "drives": drives
                }
            else:
                return {"connected": False, "error": f"HTTP {resp.status_code}", "drives": []}
        except Exception as e:
            return {"connected": False, "error": str(e), "drives": []}

    async def get_airing_watch_url(self, airing_path: str) -> Dict[str, Any]:
        """Request watch session for an airing or channel. Returns playlist_url."""
        if not self.device:
            raise RuntimeError("Not authenticated")

        # Normalize path
        if not airing_path.startswith("/"):
            airing_path = "/" + airing_path

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
            "device_id": self.device.client_id,
            "platform": "ios",
        })

        # Try watch endpoints:
        # 1. POST {airing_path}/watch
        # 2. POST /watch with path in body
        watch_path = f"{airing_path}/watch"
        resp = await self.request_local("POST", watch_path, body)

        if resp.status_code in (404, 400):
            # Try alternate watch endpoint:
            resp = await self.request_local("POST", "/watch", json.dumps({"path": airing_path}))

        if resp.status_code == 401:
            raise RuntimeError("Tablo 401 Unauthorized: Session token expired or device rebooted.")

        resp.raise_for_status()
        data = resp.json()
        return data

    async def end_watch_session(self, token: Optional[str]) -> None:
        """Tell the Tablo a watch session is over, so it frees the tuner straight away. Without this
        it keeps the tuner reserved until the session times out on its own, and closing a few
        channels in a row ties up every tuner. Never raises."""
        if not token or not self.device:
            return
        try:
            resp = await self.request_local("DELETE", f"/player/sessions/{token}")
            if resp.status_code not in (200, 204, 404):
                print(f"[TabloManager] Ending watch session: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[TabloManager] Couldn't end a watch session: {e}")

    async def delete_airing(self, airing_path: str) -> bool:
        """Send signed DELETE request to local Tablo device."""
        if not self.device:
            raise RuntimeError("Not authenticated")

        if not airing_path.startswith("/"):
            airing_path = "/" + airing_path

        resp = await self.request_local("DELETE", airing_path)
        # 404 means the recording is already gone from the device
        return resp.status_code in (200, 204, 404)


tablo_manager = TabloManager()
