"""System status, hard drive storage metrics, library refresh, and export tracking."""

import asyncio
import shutil
import socket
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel
from ..config import APP_NAME, APP_VERSION, IS_PACKAGED, FFMPEG_PATH, HOME_DIR, DOWNLOADS_DIR
from ..settings import load_settings, save_settings
from ..tablo_client import tablo_manager
from ..sync_service import sync_service
from ..database import get_sync_meta, get_export_jobs, delete_export_job

router = APIRouter(prefix="/api", tags=["system"])


class SettingsUpdate(BaseModel):
    allow_lan: Optional[bool] = None


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
        "ffmpeg_found": Path(FFMPEG_PATH).is_file() or shutil.which(FFMPEG_PATH) is not None,
        "listening_on_network": host not in ("127.0.0.1", "localhost") if host else None,
        "network_url": f"http://{lan_ip}:{port}" if lan_ip and port else None,
        "data_dir": str(HOME_DIR),
        "downloads_dir": str(DOWNLOADS_DIR),
    }


@router.get("/settings")
async def get_settings(request: Request):
    return {**load_settings(), "can_apply_now": hasattr(request.app.state, "request_restart")}


@router.post("/settings")
async def update_settings(update: SettingsUpdate, request: Request):
    """Save settings. In the packaged app the launcher restarts the server to apply network changes."""
    saved = save_settings(update.model_dump(exclude_none=True))
    restart = getattr(request.app.state, "request_restart", None)
    if restart:
        # Let this response go out first, then rebind
        asyncio.get_running_loop().call_later(0.5, restart)
    return {**saved, "restarting": bool(restart), "restart_required": not restart}


@router.get("/storage")
async def get_storage():
    """Fetch storage usage from Tablo attached hard drive(s)."""
    return await tablo_manager.get_storage_info()


@router.post("/library/refresh")
async def refresh_library():
    """Trigger library refresh from Tablo DVR hardware."""
    if sync_service.is_syncing:
        return {"status": "in_progress", "message": "Sync is already in progress"}

    # Start sync task in background
    task = asyncio.create_task(sync_service.sync_library())
    return {"status": "started", "message": "Library sync initiated"}


@router.get("/library/status")
async def get_library_status():
    """Check status of background library sync."""
    last_sync = get_sync_meta("last_sync")
    total_shows = get_sync_meta("total_shows") or "0"
    total_episodes = get_sync_meta("total_episodes") or "0"

    return {
        "is_syncing": sync_service.is_syncing,
        "last_sync": last_sync,
        "last_error": sync_service.last_error,
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
