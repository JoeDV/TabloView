"""PIN for other devices on the home network (when "Allow other devices on my network" is on).

The PC running TabloView is never asked (requests passed on through it, by Tailscale Serve or a proxy,
are asked: see PROXY_HEADERS). Another device signs in once with the PIN and is remembered
for REMEMBER_DAYS by a signed cookie; changing the PIN or "Sign out other devices" ends every
remembered device (the cookie carries a generation number). The PIN is kept only as a salted scrypt
hash. After MAX_TRIES wrong PINs from one address, that address waits LOCKOUT_SECONDS, twice as long
each time it happens again (up to LOCKOUT_MAX_SECONDS), until the right PIN or a quiet day.

Sign-ins, wrong PINs and lockouts are kept in ACTIVITY_FILE, with the devices that used TabloView and
when, for the Device page (on this PC only).

Pages, scripts and styles stay public (they hold no data); /api/* and /downloads/* need the PIN.
"""

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import threading
import time
from typing import Dict, Mapping, Optional, Tuple

from .config import DATA_DIR
from .settings import load_settings, save_settings

COOKIE = "tabloview_device"
REMEMBER_DAYS = 90
MAX_TRIES = 5
LOCKOUT_SECONDS = 60
LOCKOUT_MAX_SECONDS = 3600
LOCKOUT_FORGET_SECONDS = 86400  # a day without a lockout: the next one is short again
PUBLIC_PATHS = {"/api/lan/status", "/api/lan/login"}

ACTIVITY_FILE = DATA_DIR / "lan_activity.json"
EVENTS_KEPT = 100
DEVICES_KEPT = 30
SEEN_EVERY = 300  # a signed-in device's last use is written at most this often

# address -> (wrong tries, locked until, lockouts so far)
_failures: Dict[str, Tuple[int, float, int]] = {}
_seen_written: Dict[str, float] = {}
# PIN checks run in a worker thread (the hash takes a moment on purpose), one at a time: the wrong-try
# counts stay exact, and a flood of attempts can't use more than one CPU core
_check_lock = threading.Lock()


# Added by something that passes on requests from elsewhere: Tailscale Serve and Funnel (Funnel is the
# open internet), reverse proxies. Their requests reach TabloView from this PC's own address, but come
# from another device, so they need the PIN like any other.
PROXY_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip",
                 "tailscale-user-login", "tailscale-funnel-request")


def is_local(client_host: Optional[str], headers: Optional[Mapping[str, str]] = None) -> bool:
    """The request comes from this PC itself, not passed on from another device."""
    if headers is not None and any(h in headers for h in PROXY_HEADERS):
        return False
    try:
        return ipaddress.ip_address(client_host or "").is_loopback
    except ValueError:
        return False


def client_address(request) -> Optional[str]:
    return request.client.host if request.client else None


def from_this_pc(request) -> bool:
    return is_local(client_address(request), request.headers)


def valid_pin(pin: str) -> bool:
    return pin.isdigit() and 4 <= len(pin) <= 6


def _hash(pin: str, salt: str) -> str:
    return hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex()


def pin_set() -> bool:
    return bool(load_settings().get("lan_pin"))


def set_pin(pin: str) -> None:
    """Set or change the PIN; every remembered device has to sign in again."""
    salt = secrets.token_hex(16)
    s = load_settings()
    save_settings({"lan_pin": {"salt": salt, "hash": _hash(pin, salt)},
                   "lan_secret": s.get("lan_secret") or secrets.token_hex(32),
                   "lan_generation": int(s.get("lan_generation") or 0) + 1})


def sign_out_all() -> None:
    save_settings({"lan_generation": int(load_settings().get("lan_generation") or 0) + 1})


def _sign(payload: str, secret: str) -> str:
    return hmac.new(bytes.fromhex(secret), payload.encode(), hashlib.sha256).hexdigest()[:40]


def make_token(now: Optional[float] = None) -> str:
    s = load_settings()
    payload = f"{int(s.get('lan_generation') or 0)}.{int((now or time.time()) + REMEMBER_DAYS * 86400)}"
    return f"{payload}.{_sign(payload, s['lan_secret'])}"


def token_ok(token: Optional[str], now: Optional[float] = None) -> bool:
    s = load_settings()
    if not token or not s.get("lan_secret") or token.count(".") != 2:
        return False
    generation, expires, sig = token.split(".")
    payload = f"{generation}.{expires}"
    return (hmac.compare_digest(sig, _sign(payload, s["lan_secret"]))
            and generation == str(int(s.get("lan_generation") or 0))
            and expires.isdigit() and int(expires) > (now or time.time()))


def check_pin(pin: str, address: str, now: Optional[float] = None) -> Tuple[bool, int]:
    """(right PIN, seconds to wait before trying again)."""
    with _check_lock:
        return _check_pin(pin, address, now or time.time())


def _check_pin(pin: str, address: str, now: float) -> Tuple[bool, int]:
    tries, until, lockouts = _failures.get(address, (0, 0.0, 0))
    if until > now:
        return False, int(until - now) + 1
    if lockouts and now - until > LOCKOUT_FORGET_SECONDS:
        lockouts = 0
    stored = load_settings().get("lan_pin") or {}
    if stored and valid_pin(pin) and hmac.compare_digest(_hash(pin, stored["salt"]), stored["hash"]):
        _failures.pop(address, None)
        return True, 0
    tries += 1
    if tries >= MAX_TRIES:
        wait = min(LOCKOUT_SECONDS * 2 ** lockouts, LOCKOUT_MAX_SECONDS)
        _failures[address] = (0, now + wait, lockouts + 1)
        return False, wait
    _failures[address] = (tries, until, lockouts)
    return False, 0


def blocked(path: str, client_host: Optional[str], cookie: Optional[str],
            headers: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Why this request may not go through ('pin_required' / 'pin_not_set'), or None if it may."""
    if is_local(client_host, headers) or path in PUBLIC_PATHS:
        return None
    if not (path.startswith("/api/") or path.startswith("/downloads/")):
        return None
    if not pin_set():
        return "pin_not_set"
    return None if token_ok(cookie) else "pin_required"


# ---------------------------------------------------------------------------
# Who used TabloView from other devices: sign-ins, wrong PINs, and each device's last use
# ---------------------------------------------------------------------------
def describe_agent(ua: Optional[str]) -> str:
    """A short name for a device from its browser's User-Agent, like "Fire TV, Silk" or "iPhone, Safari"."""
    ua = ua or ""
    fire = bool(re.search(r"\bAFT", ua))
    if "TabloViewTV/" in ua:
        return "TabloView TV app" + (" on Fire TV" if fire else "")
    if fire:
        device = "Fire TV"
    elif re.search(r"GoogleTV|Google TV|Android TV|BRAVIA|CrKey|SMART-TV|SmartTV|Tizen|Web0S|webOS", ua):
        device = "TV"
    elif "iPhone" in ua:
        device = "iPhone"
    elif "iPad" in ua:
        device = "iPad"
    elif "Android" in ua:
        device = "Android"
    elif "Windows" in ua:
        device = "Windows PC"
    elif "Macintosh" in ua:
        device = "Mac"
    elif "CrOS" in ua:
        device = "Chromebook"
    elif "Linux" in ua:
        device = "Linux"
    elif "VLC" in ua:
        return "VLC"
    else:
        return "Unknown device"
    for name, pattern in (("Silk", r"Silk/"), ("TV Bro", r"TV ?Bro"), ("Edge", r"Edg/"), ("Firefox", r"Firefox/"),
                          ("VLC", r"VLC"), ("Chrome", r"Chrome/"), ("Safari", r"Safari/")):
        if re.search(pattern, ua, re.I):
            return f"{device}, {name}"
    return device


def _load_activity() -> Dict:
    try:
        data = json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"events": list(data.get("events") or []), "devices": dict(data.get("devices") or {})}
    except (OSError, ValueError):
        pass
    return {"events": [], "devices": {}}


def _save_activity(data: Dict) -> None:
    try:
        ACTIVITY_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError as e:
        print(f"[Network access] Couldn't save the sign-in record: {e}")


def _touch_device(data: Dict, address: str, device: str, now: float) -> None:
    d = data["devices"].setdefault(f"{address}|{device}", {"address": address, "device": device, "first": now})
    d["last"] = now
    extra = len(data["devices"]) - DEVICES_KEPT
    if extra > 0:  # the longest unused go
        for key in sorted(data["devices"], key=lambda k: data["devices"][k].get("last", 0))[:extra]:
            del data["devices"][key]


def note_event(address: str, ua: Optional[str], what: str, wait: int = 0, now: Optional[float] = None) -> None:
    """Record a sign-in ('signed_in'), a wrong PIN ('wrong_pin') or a lockout ('locked_out', wait = seconds)."""
    now = now or time.time()
    device = describe_agent(ua)
    data = _load_activity()
    event = {"time": now, "address": address, "device": device, "what": what}
    if wait:
        event["wait"] = wait
    data["events"] = ([event] + data["events"])[:EVENTS_KEPT]
    if what == "signed_in":
        _touch_device(data, address, device, now)
        _seen_written[f"{address}|{device}"] = now
    _save_activity(data)


def note_seen(address: Optional[str], ua: Optional[str], now: Optional[float] = None) -> None:
    """A signed-in device used TabloView: keep its last use (written every few minutes at most)."""
    if not address:
        return
    now = now or time.time()
    device = describe_agent(ua)
    key = f"{address}|{device}"
    if now - _seen_written.get(key, 0) < SEEN_EVERY:
        return
    _seen_written[key] = now
    data = _load_activity()
    _touch_device(data, address, device, now)
    _save_activity(data)


def activity(now: Optional[float] = None) -> Dict:
    """Devices by last use and sign-in events, newest first, and the wrong PINs in the last day."""
    now = now or time.time()
    data = _load_activity()
    return {"devices": sorted(data["devices"].values(), key=lambda d: d.get("last", 0), reverse=True),
            "events": data["events"],
            "wrong_pins_today": sum(1 for e in data["events"]
                                    if e.get("what") in ("wrong_pin", "locked_out") and e.get("time", 0) > now - 86400)}


def clear_activity() -> None:
    _seen_written.clear()
    _save_activity({"events": [], "devices": {}})
