"""Reports whether a newer TabloView is available: from the published version.json for installer copies,
and from the Microsoft Store itself for Store copies (the Store installs the update; this only tells
the user it's there)."""

import os
import re
import sys
import time
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx

from .config import APP_VERSION, UPDATE_INFO_URL, IS_STORE, STORE_LINK

CHECK_EVERY_SECONDS = 6 * 3600
_cache: Dict[str, Any] = {"checked": 0.0, "result": None}


def _version_tuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4]) or (0,)


def update_url() -> str:
    return direct_download_url((os.getenv("TABLOVIEW_UPDATE_URL") or UPDATE_INFO_URL or "").strip())


def direct_download_url(url: str) -> str:
    """OneDrive / SharePoint 'anyone with the link' share links open a preview page; adding
    download=1 makes them return the file itself."""
    if not url:
        return url
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if any(h in host for h in ("1drv.ms", "onedrive.live.com", "sharepoint.com")):
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["download"] = "1"
        return urlunsplit(parts._replace(query=urlencode(query)))
    return url


async def store_update_version() -> Optional[str]:
    """The newer version of this app the Microsoft Store has for this PC, or None."""
    from winrt.windows.services.store import StoreContext
    found = await StoreContext.get_default().get_app_and_optional_store_package_updates_async()
    for update in found:
        v = update.package.id.version
        return f"{v.major}.{v.minor}.{v.build}"
    return None


async def check_for_update(force: bool = False) -> Dict[str, Any]:
    """Return {'current', 'latest', 'update_available', 'download_url', 'notes', 'error', 'store'}.
    Results are cached for CHECK_EVERY_SECONDS; failures never raise."""
    # The published download is a Windows installer; Store copies ask the Store instead
    url = "" if IS_STORE or sys.platform != "win32" else update_url()
    base: Dict[str, Any] = {"current": APP_VERSION, "latest": None, "update_available": False,
                            "download_url": STORE_LINK if IS_STORE else None, "notes": None, "error": None,
                            "enabled": bool(url) or IS_STORE, "store": IS_STORE}
    if not base["enabled"]:
        return base
    if not force and _cache["result"] and time.time() - _cache["checked"] < CHECK_EVERY_SECONDS:
        return _cache["result"]

    result = dict(base)
    if IS_STORE:
        try:
            latest = await store_update_version()
            result.update(latest=latest, update_available=bool(latest) and _version_tuple(latest) > _version_tuple(APP_VERSION))
        except Exception as e:
            result["error"] = f"Couldn't check the Microsoft Store: {e}"
            print(f"[Updates] {result['error']}")
        _cache.update(checked=time.time(), result=result)
        return result

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Cache-Control": "no-cache"})
        resp.raise_for_status()
        info = resp.json()
        latest: Optional[str] = str(info.get("version") or "").strip() or None
        result.update({
            "latest": latest,
            "download_url": info.get("download_url"),
            "notes": info.get("notes"),
            "update_available": bool(latest) and _version_tuple(latest) > _version_tuple(APP_VERSION),
        })
    except Exception as e:
        result["error"] = f"Couldn't check for updates: {e}"
        print(f"[Updates] {result['error']}")

    _cache.update(checked=time.time(), result=result)
    return result
