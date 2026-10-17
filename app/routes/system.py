"""System status, hard drive storage metrics, library refresh, and export tracking."""

import asyncio
from pathlib import Path
from fastapi import APIRouter
from ..tablo_client import tablo_manager
from ..sync_service import sync_service
from ..database import get_sync_meta, get_export_jobs, delete_export_job

router = APIRouter(prefix="/api", tags=["system"])


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
