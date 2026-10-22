"""Debug and endpoint probe inspector helper route."""

import platform
import time
import httpx
from fastapi import APIRouter
from typing import Dict, Any

from ..config import APP_VERSION, IS_PACKAGED, IS_STORE
from ..tablo_client import tablo_manager

router = APIRouter(prefix="/api/debug", tags=["debug"])


def mask(secret: str) -> str:
    """The first and last 4 characters, so people can tell tokens apart without sharing them."""
    return f"{secret[:4]}…{secret[-4:]}" if secret and len(secret) > 12 else "…"


def _hide_tokens(text: str, *secrets: str) -> str:
    """The output is made to be pasted into forum posts and issues: no sign-in tokens in it
    (the cloud path, and error messages that repeat the URL, contain the Lighthouse token)."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, mask(secret))
    return text


@router.get("/endpoints")
async def probe_endpoints():
    """Probe standard local and cloud endpoints for Tablo 4th Gen diagnosis."""
    if not tablo_manager.is_authenticated:
        return {
            "authenticated": False,
            "error": "Tablo device is not authenticated. Please log in first."
        }

    dev = tablo_manager.device
    local_endpoints = [
        ("GET", "/ping"),
        ("GET", "/server/info"),
        ("GET", "/server/harddrives"),
        ("GET", "/recordings/airings"),
        ("GET", "/recordings/series"),
        ("GET", "/recordings/shows"),
        ("GET", "/recordings/movies"),
        ("GET", "/recordings/sports"),
        ("GET", "/guide/channels"),
    ]

    results: Dict[str, Any] = {
        # Which TabloView sent this: the first question when someone shares it
        "tabloview": {
            "version": APP_VERSION,
            "edition": "Microsoft Store" if IS_STORE else "installer" if IS_PACKAGED else "source",
            "os": f"{platform.system()} {platform.release()}",
        },
        "device": {
            "name": dev.name,
            "sid": dev.sid,
            "local_url": dev.local_url,
            "client_id": mask(dev.client_id)
        },
        "probes": []
    }

    # Test local endpoints
    for method, path in local_endpoints:
        start_t = time.monotonic()
        try:
            if path == "/ping":
                # Unauthenticated
                r = await tablo_manager._http.get(f"{dev.local_url.rstrip('/')}/ping", timeout=5)
            else:
                r = await tablo_manager.request_local(method, path)

            elapsed_ms = round((time.monotonic() - start_t) * 1000, 1)
            preview = None
            item_count = None
            if r.status_code == 200:
                try:
                    data = r.json()
                    item_count = len(data) if isinstance(data, list) else len(data.keys())
                    preview = data[:3] if isinstance(data, list) else data
                except Exception:
                    preview = r.text[:200]

            results["probes"].append({
                "target": "local",
                "method": method,
                "path": path,
                "status_code": r.status_code,
                "elapsed_ms": elapsed_ms,
                "item_count": item_count,
                "preview": preview,
                "success": r.status_code == 200
            })
        except Exception as e:
            elapsed_ms = round((time.monotonic() - start_t) * 1000, 1)
            results["probes"].append({
                "target": "local",
                "method": method,
                "path": path,
                "status_code": None,
                "elapsed_ms": elapsed_ms,
                "error": _hide_tokens(str(e), dev.lighthouse_token, dev.account_token),
                "success": False
            })

    # Test cloud guide endpoint
    cloud_path = f"/api/v2/account/{dev.lighthouse_token}/guide/channels/"
    cloud_url = f"https://lighthousetv.ewscloud.com{cloud_path}"
    start_t = time.monotonic()
    try:
        c_resp = await tablo_manager._http.get(
            cloud_url,
            headers={
                "Authorization": f"Bearer {dev.account_token}",
                "Lighthouse": dev.lighthouse_token,
                "User-Agent": "Tablo-FAST/2.0.0 (Mobile; iPhone; iOS 16.6)",
                "Accept": "*/*",
            },
            timeout=10
        )
        elapsed_ms = round((time.monotonic() - start_t) * 1000, 1)
        data = c_resp.json() if c_resp.status_code == 200 else None
        results["probes"].append({
            "target": "cloud",
            "method": "GET",
            "path": _hide_tokens(cloud_path, dev.lighthouse_token),
            "status_code": c_resp.status_code,
            "elapsed_ms": elapsed_ms,
            "item_count": len(data) if isinstance(data, list) else None,
            "preview": data[:3] if isinstance(data, list) else None,
            "success": c_resp.status_code == 200
        })
    except Exception as e:
        results["probes"].append({
            "target": "cloud",
            "method": "GET",
            "path": _hide_tokens(cloud_path, dev.lighthouse_token),
            "status_code": None,
            "elapsed_ms": round((time.monotonic() - start_t) * 1000, 1),
            "error": _hide_tokens(str(e), dev.lighthouse_token, dev.account_token),
            "success": False
        })

    return results
