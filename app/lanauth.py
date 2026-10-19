"""PIN for other devices on the home network (when "Allow other devices on my network" is on).

The PC running TabloView is never asked. Another device signs in once with the PIN and is remembered
for REMEMBER_DAYS by a signed cookie; changing the PIN or "Sign out other devices" ends every
remembered device (the cookie carries a generation number). The PIN is kept only as a salted scrypt
hash. After MAX_TRIES wrong PINs from one address, that address waits LOCKOUT_SECONDS.

Pages, scripts and styles stay public (they hold no data); /api/* and /downloads/* need the PIN.
"""

import hashlib
import hmac
import ipaddress
import secrets
import time
from typing import Dict, Optional, Tuple

from .settings import load_settings, save_settings

COOKIE = "tabloview_device"
REMEMBER_DAYS = 90
MAX_TRIES = 5
LOCKOUT_SECONDS = 60
PUBLIC_PATHS = {"/api/lan/status", "/api/lan/login"}

_failures: Dict[str, Tuple[int, float]] = {}  # address -> (wrong tries, locked until)


def is_local(client_host: Optional[str]) -> bool:
    """The request comes from this PC itself."""
    try:
        return ipaddress.ip_address(client_host or "").is_loopback
    except ValueError:
        return False


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
    now = now or time.time()
    tries, until = _failures.get(address, (0, 0.0))
    if until > now:
        return False, int(until - now) + 1
    stored = load_settings().get("lan_pin") or {}
    if stored and valid_pin(pin) and hmac.compare_digest(_hash(pin, stored["salt"]), stored["hash"]):
        _failures.pop(address, None)
        return True, 0
    tries += 1
    if tries >= MAX_TRIES:
        _failures[address] = (0, now + LOCKOUT_SECONDS)
        return False, LOCKOUT_SECONDS
    _failures[address] = (tries, 0.0)
    return False, 0


def blocked(path: str, client_host: Optional[str], cookie: Optional[str]) -> Optional[str]:
    """Why this request may not go through ('pin_required' / 'pin_not_set'), or None if it may."""
    if is_local(client_host) or path in PUBLIC_PATHS:
        return None
    if not (path.startswith("/api/") or path.startswith("/downloads/")):
        return None
    if not pin_set():
        return "pin_not_set"
    return None if token_ok(cookie) else "pin_required"
