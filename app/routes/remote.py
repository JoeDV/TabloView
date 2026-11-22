"""Phone as a remote (app/remote.py): TV views ask here for their commands, phones send them."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import lanauth, remote

router = APIRouter(prefix="/api/remote", tags=["remote"])

ScreenId = Query(..., min_length=6, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


def _name(request: Request, name: Optional[str]) -> str:
    return (name or "").strip()[:40] or lanauth.describe_agent(request.headers.get("user-agent"))


@router.get("/next")
async def next_commands(request: Request, screen: str = ScreenId, name: Optional[str] = Query(None, max_length=40)):
    """A TV view waiting for what a phone sends (up to a few seconds; then it asks again)."""
    return {"commands": await remote.wait_for_commands(screen, _name(request, name))}


class StateUpdate(BaseModel):
    screen: str = Field(min_length=6, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: Optional[str] = Field(default=None, max_length=40)
    state: Dict[str, Any] = Field(default_factory=dict)


@router.post("/state")
async def screen_state(req: StateUpdate, request: Request):
    """What a TV view shows now (the page, or what's playing), for the phones."""
    state = {k: v for k, v in req.state.items() if isinstance(v, (str, int, float, bool)) or v is None}
    remote.set_state(req.screen, _name(request, req.name), {k: (v[:200] if isinstance(v, str) else v) for k, v in state.items()})
    return {"success": True}


@router.get("/screens")
async def list_screens():
    return {"screens": remote.listed()}


class Command(BaseModel):
    screen: str = Field(min_length=6, max_length=40)
    command: str = Field(max_length=20)
    value: Optional[str] = Field(default=None, max_length=300)


@router.post("/send")
async def send(req: Command):
    try:
        remote.send(req.screen, req.command, req.value)
    except remote.RemoteError as e:
        raise HTTPException(status_code=404 if "isn't open" in str(e) else 400, detail=str(e))
    return {"success": True}
