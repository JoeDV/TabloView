"""System status, hard drive storage metrics, library refresh, and export tracking."""

import asyncio
import shutil
import socket
import time
from pathlib import Path
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from ..config import APP_NAME, APP_VERSION, IS_PACKAGED, IS_STORE, FFMPEG_PATH, HOME_DIR, DOWNLOADS_DIR
from ..settings import load_settings, save_settings
from ..updates import check_for_update
from .. import encoders, notifications, startup, whatsnew
from ..tablo_client import tablo_manager
from ..sync_service import sync_service
from ..database import get_sync_meta, get_export_jobs, delete_export_job, get_storage_by_show

router = APIRouter(prefix="/api", tags=["system"])


class SettingsUpdate(BaseModel):
    allow_lan: Optional[bool] = None
    auto_sync_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    notifications: Optional[bool] = None
    video_quality: Optional[Literal["auto", "best", "fastest"]] = None
    smooth_motion: Optional[bool] = None
    export_format: Optional[Literal["smaller", "original"]] = None
    rerecord_failed: Optional[bool] = None


class StartupUpdate(BaseModel):
    enabled: bool


def _lan_ip() -> Optional[str]:
    """This PC's address on the home network (no packets are sent by a UDP connect)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


@router.get("/system/info")
async def system_info(request: Request):
    """App version, where it is listening, and whether FFmpeg is available."""
    runtime = getattr(request.app.state, "runtime", None) or {}
    host = runtime.get("host")
    port = runtime.get("port") or request.url.port
    lan_ip = _lan_ip()
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "packaged": IS_PACKAGED,
        "store": IS_STORE,
        "ffmpeg_found": Path(FFMPEG_PATH).is_file() or shutil.which(FFMPEG_PATH) is not None,
        "listening_on_network": host not in ("127.0.0.1", "localhost") if host else None,
        "network_url": f"http://{lan_ip}:{port}" if lan_ip and port else None,
        "data_dir": str(HOME_DIR),
        "downloads_dir": str(DOWNLOADS_DIR),
    }


@router.get("/system/update")
async def update_status(force: bool = False):
    """Is a newer TabloView published? (checked at most every few hours unless force=true)"""
    return await check_for_update(force=force)


@router.get("/settings")
async def get_settings(request: Request):
    return {**load_settings(), "can_apply_now": hasattr(request.app.state, "request_restart")}


@router.post("/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    """Save settings. Only a network-access change needs a restart (to rebind); in the packaged app
    the launcher does that automatically. Auto-sync changes apply within a minute."""
    changes = update.model_dump(exclude_none=True)
    needs_restart = "allow_lan" in changes and changes["allow_lan"] != load_settings().get("allow_lan")
    saved = save_settings(changes)
    restart = getattr(request.app.state, "request_restart", None) if needs_restart else None
    if restart:
        # Let this response go out first, then rebind
        asyncio.get_running_loop().call_later(0.5, restart)
    return {**saved, "restarting": bool(restart), "restart_required": needs_restart and not restart}


@router.get("/storage")
async def get_storage():
    """Fetch storage usage from Tablo attached hard drive(s)."""
    return await tablo_manager.get_storage_info()


@router.get("/system/startup")
async def get_startup():
    """Whether TabloView starts (in the tray) when the user signs in to Windows."""
    return {**await startup.get_state(), "notifications_available": notifications.available()}


@router.post("/system/startup")
async def set_startup(update: StartupUpdate):
    try:
        return await startup.set_enabled(update.enabled)
    except Exception as e:
        print(f"[Startup] Couldn't change the startup setting: {e}")
        raise HTTPException(status_code=500, detail=f"Couldn't change the startup setting: {e}")


@router.get("/system/whatsnew")
async def get_whatsnew():
    """Release notes to show once after an update."""
    return whatsnew.pending()


@router.get("/system/changelog")
async def get_changelog():
    """What changed in each version, newest first."""
    return {"current": APP_VERSION, "versions": whatsnew.changelog()}


@router.post("/system/whatsnew/seen")
async def whatsnew_seen():
    whatsnew.mark_seen()
    return {"success": True}


@router.get("/system/playback")
async def get_playback():
    """Which video encoder playback uses on this PC, and the effective settings."""
    settings = load_settings()
    enc = await asyncio.to_thread(encoders.choose, settings.get("video_quality") or "auto")
    return {
        "encoder": enc["label"],
        "hardware": enc["hardware"],
        "quality": settings.get("video_quality") or "auto",
        "smooth_motion": bool(settings.get("smooth_motion")) and enc["name"] != "fastest",
    }


@router.get("/storage/shows")
async def get_storage_shows():
    """Which shows use the most space, and how much of it is watched (deletable) recordings."""
    shows = get_storage_by_show()
    return {"shows": shows, "total_bytes": sum(s["bytes"] for s in shows)}


@router.post("/library/refresh")
async def refresh_library():
    """Trigger library refresh from Tablo DVR hardware."""
    if sync_service.is_syncing:
        return {"status": "in_progress", "message": "Sync is already in progress"}

    # Start sync task in background
    task = asyncio.create_task(sync_service.sync_library())
    return {"status": "started", "message": "Library sync initiated"}


_last_recheck = 0.0


async def recheck_tablo() -> None:
    """While the Tablo is marked as not answering, try it again at most every 15 s, so the banner
    clears even on pages that don't otherwise contact the Tablo."""
    global _last_recheck
    if not tablo_manager.tablo_unreachable or time.time() - _last_recheck < 15:
        return
    _last_recheck = time.time()
    try:
        await asyncio.wait_for(tablo_manager.request_local("GET", "/server/info"), timeout=6)
    except Exception:
        pass  # still not answering; request_local keeps it marked


def guide_progress() -> Optional[dict]:
    """A long guide load in progress, with a rough time left once there's enough to go on."""
    p = sync_service.guide_progress
    if not p:
        return None
    now = time.time()
    out = {"first": p["first"], "step": p["step"], "done": p["done"], "total": p["total"],
           "minutes_left": None, "waiting_seconds": None}
    if p.get("waiting_until"):
        out["waiting_seconds"] = max(0, round(p["waiting_until"] - now))
    if p["step"] == "airings" and p["done"] >= 100 and p["total"] > p["done"]:
        rate = p["done"] / max(1.0, now - p["started"])
        out["minutes_left"] = max(1, round((p["total"] - p["done"]) / rate / 60))
    return out


@router.get("/library/status")
async def get_library_status():
    """Check status of background library sync."""
    await recheck_tablo()
    last_sync = get_sync_meta("last_sync")
    total_shows = get_sync_meta("total_shows") or "0"
    total_episodes = get_sync_meta("total_episodes") or "0"

    return {
        "is_syncing": sync_service.is_syncing,
        "last_sync": last_sync,
        "last_error": sync_service.last_error,
        "auth_problem": tablo_manager.auth_problem,
        "tablo_unreachable": tablo_manager.tablo_unreachable,
        "guide_progress": guide_progress(),
        "total_shows": int(total_shows),
        "total_episodes": int(total_episodes)
    }


@router.get("/exports")
async def list_exports():
    """List recent MP4 export jobs and their download status.
    Completed exports whose file was deleted from ./downloads are dropped from the list."""
    jobs = []
    for job in get_export_jobs():
        if job.get("status") == "completed" and not Path(job.get("filepath") or "").is_file():
            delete_export_job(job["job_id"])
            continue
        jobs.append(job)
    return {"jobs": jobs}
