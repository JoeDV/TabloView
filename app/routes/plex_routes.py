"""Device → Plex: sign in to Plex, choose the server, and have it scan new exports (app/plex.py)."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import plex
from ..settings import exports_dir, save_settings
from .system import _only_this_pc

router = APIRouter(prefix="/api/plex", tags=["plex"])


class ServerChoice(BaseModel):
    id: str


class PlexSettings(BaseModel):
    scan: bool


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
    save_settings({"plex_scan": update.scan})
    return {"scan": update.scan}


@router.post("/scan")
async def plex_scan_now(request: Request):
    """Scan the export folder in Plex now (also a test of the connection and the library match)."""
    _only_this_pc(request)
    try:
        return {"message": await plex.scan(exports_dir())}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Couldn't reach Plex: {e}")


@router.post("/signout")
async def plex_signout(request: Request):
    _only_this_pc(request)
    plex.sign_out()
    return {"signed_in": False}
