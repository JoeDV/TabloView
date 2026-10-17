"""Authentication and device discovery routes."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from ..tablo_client import tablo_manager
from ..sync_service import sync_service
from ..database import get_sync_meta

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/status")
async def get_auth_status():
    last_sync = get_sync_meta("last_sync")
    total_shows = get_sync_meta("total_shows") or "0"
    total_episodes = get_sync_meta("total_episodes") or "0"

    dev = tablo_manager.device
    return {
        "authenticated": tablo_manager.is_authenticated,
        "email": tablo_manager.email,
        "active_device": {
            "name": dev.name if dev else None,
            "sid": dev.sid if dev else None,
            "local_url": dev.local_url if dev else None,
        } if dev else None,
        "devices": [
            {"name": d.name, "sid": d.sid, "local_url": d.local_url}
            for d in tablo_manager.devices
        ],
        "last_sync": last_sync,
        "total_shows": int(total_shows),
        "total_episodes": int(total_episodes),
        "is_syncing": sync_service.is_syncing
    }


@router.post("/login")
async def login(req: LoginRequest):
    try:
        devices = await tablo_manager.login(req.email, req.password)
        # Trigger background library sync automatically on login
        asyncio.create_task(sync_service.sync_library())
        return {
            "success": True,
            "devices_count": len(devices),
            "active_device": {
                "name": tablo_manager.device.name,
                "sid": tablo_manager.device.sid,
                "local_url": tablo_manager.device.local_url,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/select/{sid}")
async def select_device(sid: str):
    try:
        dev = tablo_manager.select_device(sid)
        asyncio.create_task(sync_service.sync_library())
        return {
            "success": True,
            "active_device": {"name": dev.name, "sid": dev.sid, "local_url": dev.local_url}
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/logout")
async def logout():
    tablo_manager.logout()
    return {"success": True}
