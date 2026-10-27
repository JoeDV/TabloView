"""Authentication and device discovery routes."""

import re
import json
import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from .. import lanauth
from ..tablo_client import tablo_manager
from ..sync_service import sync_service
from ..database import get_sync_meta

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _only_this_pc(request: Request) -> None:
    """Signing in to the Tablo account, choosing the Tablo and signing out happen on the PC running
    TabloView: a device with the PIN could otherwise sign it out, or into someone else's account."""
    if not lanauth.from_this_pc(request):
        raise HTTPException(status_code=403, detail="Sign in to your Tablo account on the PC running TabloView.")


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/status")
async def get_auth_status(request: Request):
    last_sync = get_sync_meta("last_sync")
    total_shows = get_sync_meta("total_shows") or "0"
    total_episodes = get_sync_meta("total_episodes") or "0"

    dev = tablo_manager.device
    return {
        "authenticated": tablo_manager.is_authenticated,
        "email": tablo_manager.email if lanauth.from_this_pc(request) else None,  # the account's: this PC only
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
        "is_syncing": sync_service.is_syncing,
        "auth_problem": tablo_manager.auth_problem,
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    _only_this_pc(request)
    try:
        # Autofill often adds a space after the email, which Tablo's sign-in rejects as a wrong email
        devices = await tablo_manager.login(req.email.strip(), req.password)
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
        raise HTTPException(status_code=400, detail=_readable_login_error(e))


def _readable_login_error(e: Exception) -> str:
    """Tablo's cloud errors arrive as 'Login failed (401): {json}'; surface just its message."""
    text = str(e)
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if data.get("code") == "password_min_length":
                return "Tablo passwords are at least 8 characters long."
            if data.get("message"):
                return data["message"]
        except ValueError:
            pass
    return text


@router.post("/select/{sid}")
async def select_device(sid: str, request: Request):
    _only_this_pc(request)
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
async def logout(request: Request):
    _only_this_pc(request)
    tablo_manager.logout()
    return {"success": True}
