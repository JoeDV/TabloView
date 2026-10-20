"""System status, hard drive storage metrics, library refresh, and export tracking."""

import asyncio
import shutil
import subprocess
import sys
import socket
import time
from pathlib import Path
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ..config import APP_NAME, APP_VERSION, IS_PACKAGED, IS_STORE, FFMPEG_PATH, HOME_DIR, DOWNLOADS_DIR
from ..settings import load_settings, save_settings, exports_dir
from ..updates import check_for_update
from .. import commercials, encoders, lanauth, notifications, startup, whatsnew
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
    skip_commercials: Optional[bool] = None


class ExportFolderRequest(BaseModel):
    path: Optional[str] = None  # None = back to the default (Downloads\\TabloView)


class PinRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=6)


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
        "lan_pin_set": lanauth.pin_set(),
        "data_dir": str(HOME_DIR),
        "downloads_dir": str(exports_dir()),
        "default_downloads_dir": str(DOWNLOADS_DIR),
    }


@router.get("/lan/status")
async def lan_status(request: Request):
    """Whether this device is the PC itself, whether a PIN is set, and whether this device is signed in."""
    local = lanauth.is_local(request.client.host if request.client else None)
    return {"local": local, "pin_set": lanauth.pin_set(),
            "signed_in": local or lanauth.token_ok(request.cookies.get(lanauth.COOKIE))}


@router.post("/lan/login")
async def lan_login(req: PinRequest, request: Request):
    """Another device signs in with the PIN and is remembered for a while."""
    if not lanauth.pin_set():
        raise HTTPException(status_code=401, detail="Set a PIN on the PC running TabloView first (Device page).")
    ok, wait = lanauth.check_pin(req.pin, request.client.host if request.client else "?")
    if not ok:
        raise HTTPException(status_code=429 if wait else 401,
                            detail=f"Too many wrong PINs. Try again in {wait} seconds." if wait else "That PIN isn't right.")
    resp = JSONResponse({"success": True})
    resp.set_cookie(lanauth.COOKIE, lanauth.make_token(), max_age=lanauth.REMEMBER_DAYS * 86400,
                    httponly=True, samesite="strict")
    return resp


def _only_this_pc(request: Request) -> None:
    if not lanauth.is_local(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="The PIN can only be changed on the PC running TabloView.")


@router.post("/lan/pin")
async def lan_set_pin(req: PinRequest, request: Request):
    """Set or change the PIN (on this PC only). Other devices have to sign in again."""
    _only_this_pc(request)
    if not lanauth.valid_pin(req.pin):
        raise HTTPException(status_code=400, detail="The PIN must be 4 to 6 digits.")
    lanauth.set_pin(req.pin)
    return {"success": True}


@router.post("/lan/signout")
async def lan_sign_out_all(request: Request):
    """Every other device has to enter the PIN again."""
    _only_this_pc(request)
    lanauth.sign_out_all()
    return {"success": True}


@router.post("/system/export_folder")
async def set_export_folder(req: ExportFolderRequest, request: Request):
    """Choose where MP4 exports are saved (on this PC only). The folder is created if needed and must
    be writable."""
    _only_this_pc(request)
    path = (req.path or "").strip().strip('"')
    if path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            raise HTTPException(status_code=400, detail="Use a full folder path, like D:\\Videos\\Tablo")
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".tabloview-write-test"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"TabloView can't save to that folder: {e.strerror or e}")
        path = str(p)
    save_settings({"export_folder": path or None})
    return {"downloads_dir": str(exports_dir()), "custom": bool(path)}


@router.post("/system/pick_folder")
async def pick_folder(request: Request):
    """Show the Windows folder picker on this PC and return the folder chosen (None if cancelled)."""
    _only_this_pc(request)
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="The folder picker is only available on Windows")
    start = str(exports_dir()).replace("'", "''")
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = 'Where should TabloView save MP4 exports?'; $d.ShowNewFolderButton = $true; "
        f"$d.SelectedPath = '{start}'; "
        "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
        "if ($d.ShowDialog($owner) -eq 'OK') { $d.SelectedPath }"
    )
    try:
        r = await asyncio.to_thread(subprocess.run, ["powershell", "-NoProfile", "-STA", "-Command", script],
                                    capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"path": None}
    chosen = r.stdout.decode("utf-8", errors="replace").strip()
    return {"path": chosen or None}


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


@router.get("/system/signal")
async def signal_report():
    """Per channel: how many recordings had problems, why, and when (Device → Signal health)."""
    from .. import signal_health
    await asyncio.to_thread(signal_health.update_history)
    return {"channels": signal_health.report(), "days": signal_health.REPORT_DAYS}


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
        "commercials": commercials.summary(),
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
