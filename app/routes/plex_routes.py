"""Settings → Plex: sign in to Plex, choose the server, and have it scan new exports (app/plex.py)."""

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .. import plex
from ..database import get_episodes_by_show, get_show_by_id
from ..settings import exports_dir, load_settings, save_settings
from .system import _only_this_pc

router = APIRouter(prefix="/api/plex", tags=["plex"])


class ServerChoice(BaseModel):
    id: str


class PlexSettings(BaseModel):
    scan: Optional[bool] = None
    fix_match: Optional[bool] = None
    copy_watched: Optional[bool] = None


class ArchiveRequest(BaseModel):
    on: bool


@router.get("")
async def plex_status():
    return await plex.status()


@router.post("/signin")
async def plex_signin(request: Request):
    _only_this_pc(request)
    try:
        return await plex.start_signin()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach plex.tv: {e}")


@router.get("/signin/{pin_id}")
async def plex_signin_check(pin_id: int, request: Request):
    _only_this_pc(request)
    try:
        return {"done": await plex.check_signin(pin_id)}
    except ValueError as e:
        return {"done": True, "error": str(e)}  # signed in; choosing the server is left to the page
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach plex.tv: {e}")


@router.post("/server")
async def plex_server(choice: ServerChoice, request: Request):
    _only_this_pc(request)
    try:
        server = await plex.connect(choice.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach plex.tv: {e}")
    return {"name": server["name"]}


@router.post("/settings")
async def plex_settings(update: PlexSettings, request: Request):
    _only_this_pc(request)
    changes = {f"plex_{k}": v for k, v in update.model_dump().items() if v is not None}
    save_settings(changes)
    s = load_settings()
    return {"scan": s.get("plex_scan", True), "fix_match": s.get("plex_fix_match", True),
            "copy_watched": s.get("plex_copy_watched", True)}


@router.post("/scan")
async def plex_scan_now(request: Request):
    """Scan the export folder in Plex now (also a test of the connection and the library match)."""
    _only_this_pc(request)
    try:
        return {"message": await plex.scan(exports_dir())}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach Plex: {e}")


@router.get("/have")
async def plex_have(show_id: str = Query(...)):
    """This show's recordings that Plex has already (for the In Plex tags on its page)."""
    try:
        return {"ids": await plex.in_plex(get_episodes_by_show(show_id))}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return {"ids": [], "error": str(e)}


@router.post("/archive")
async def plex_archive(req: ArchiveRequest, request: Request, show_id: str = Query(...)):
    """Delete this show's recordings from the Tablo once Plex has their exports, or stop."""
    _only_this_pc(request)
    if not get_show_by_id(show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    plex.set_archive(show_id, req.on)
    return {"on": req.on}


@router.post("/signout")
async def plex_signout(request: Request):
    _only_this_pc(request)
    plex.sign_out()
    return {"signed_in": False}
