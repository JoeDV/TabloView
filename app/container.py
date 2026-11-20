"""Setting TabloView up from environment variables, for a server without a screen: Docker (see
DOCKER.md) or any headless Linux box. Each one is optional; without them nothing changes.

  TABLO_EMAIL, TABLO_PASSWORD   sign in to the Tablo account at start, if not signed in yet
  TABLO_DEVICE                  which Tablo, by name or server ID, when the account has several
  TABLOVIEW_NETWORK=1           Settings → Desktop & network → Allow other devices on my network
  TABLOVIEW_PIN                 the PIN other devices enter (4 to 6 digits)

These exist because some settings can only be changed from "this PC" (the sign-in, network access,
the PIN), and in a container that's the container itself: no browser there can do it.
"""

import os

from . import lanauth
from .settings import load_settings, save_settings


def _on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def pin_matches(pin: str) -> bool:
    saved = load_settings().get("lan_pin") or {}
    return bool(saved) and lanauth._hash(pin, saved["salt"]) == saved["hash"]


def apply_settings() -> None:
    """Network access and the PIN. A PIN that's already the one saved isn't set again (that would
    sign every device out at each start)."""
    if _on("TABLOVIEW_NETWORK") and not load_settings().get("allow_lan"):
        save_settings({"allow_lan": True})
        print("[Setup] Network access turned on (TABLOVIEW_NETWORK)")
    pin = (os.getenv("TABLOVIEW_PIN") or "").strip()
    if pin:
        if not lanauth.valid_pin(pin):
            print("[Setup] TABLOVIEW_PIN must be 4 to 6 digits; it wasn't used")
        elif not pin_matches(pin):
            lanauth.set_pin(pin)
            print("[Setup] PIN set from TABLOVIEW_PIN")


async def sign_in() -> None:
    """Sign in with TABLO_EMAIL and TABLO_PASSWORD when TabloView isn't signed in yet."""
    from .config import TABLO_EMAIL, TABLO_PASSWORD
    from .tablo_client import tablo_manager
    if tablo_manager.is_authenticated or not (TABLO_EMAIL and TABLO_PASSWORD):
        return
    try:
        devices = await tablo_manager.login(TABLO_EMAIL, TABLO_PASSWORD)
    except Exception as e:
        print(f"[Setup] Couldn't sign in with TABLO_EMAIL and TABLO_PASSWORD: {e}")
        return
    wanted = (os.getenv("TABLO_DEVICE") or "").strip().lower()
    if wanted:
        pick = next((d for d in devices if wanted in (d.name.lower(), d.sid.lower())), None)
        if pick:
            tablo_manager.select_device(pick.sid)
        else:
            print(f"[Setup] No Tablo called {wanted!r} on the account; using {tablo_manager.device.name}. "
                  f"Its Tablos: {', '.join(d.name for d in devices)}")
    print(f"[Setup] Signed in; using {tablo_manager.device.name}")
