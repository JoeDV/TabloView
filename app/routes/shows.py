"""Show catalog and episode listing routes."""

import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from ..database import (
    get_shows,
    get_show_by_id,
    get_episodes_by_show,
    delete_episode,
    recalculate_show_stats,
    set_episode_progress,
    get_commercials,
    show_keep,
    set_show_keep,
)
from ..tablo_client import tablo_manager
from .. import autoexport, cleanup, commercials
from ..sync_service import slugify_show_title

router = APIRouter(prefix="/api/shows", tags=["shows"])


class KeepRequest(BaseModel):
    count: Optional[int] = Field(default=None, ge=1, le=50)  # None = keep everything


class CommercialsRequest(BaseModel):
    on: bool


class AutoExportRequest(BaseModel):
    on: bool
    existing: bool = False  # also the recordings already there (otherwise only new ones)


class CleanupRequest(BaseModel):
    days: Optional[int] = Field(default=None, ge=1, le=365)  # None = off


def _with_rules(show: Optional[dict]) -> Optional[dict]:
    """Add the show's keep rule (on the Tablo) and cleanup rule (in TabloView)."""
    if show:
        show = {**show, "keep": show_keep(show), "cleanup_days": cleanup.rules().get(show["id"]),
                "find_commercials": show["id"] in commercials.enabled_shows(),
                "auto_export": show["id"] in autoexport.enabled_shows()}
    return show


@router.get("")
async def list_shows(
    category: Optional[str] = Query(None, description="All, series, movies, sports"),
    search: Optional[str] = Query(None, description="Filter show titles as user types"),
    sort: str = Query("recent", description="recent, alphabetical, episodes")
):
    shows = get_shows(category=category, search=search, sort_by=sort)
    return {
        "count": len(shows),
        "shows": shows
    }


@router.get("/episodes")
async def get_show_episodes_query(show_id: str = Query(...)):
    """Fetch all episodes for a show by query param (handles paths with slashes)."""
    show = get_show_by_id(show_id)
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    episodes = _with_commercials(get_episodes_by_show(show_id))
    return {
        "show": _with_rules(show),
        "show_id": show_id,
        "show_title": show["title"],
        "count": len(episodes),
        "episodes": episodes,
        # Recorded already and not exported: what turning on automatic export would ask about
        "auto_export_existing": autoexport.already_recorded(show_id),
    }


@router.post("/delete_watched")
async def delete_watched_query(show_id: str = Query(...)):
    """Delete all watched episodes for this show, except ones protected on the Tablo."""
    episodes = get_episodes_by_show(show_id)
    watched = [ep for ep in episodes if ep.get("status") == "Watched" and not ep.get("protected")]
    kept = sum(1 for ep in episodes if ep.get("status") == "Watched" and ep.get("protected"))

    deleted_ids = []
    errors = []

    for ep in watched:
        ep_id = ep["id"]
        ep_path = ep.get("path")
        try:
            if not tablo_manager.is_authenticated:
                raise RuntimeError("Tablo device is not connected")
            if not await tablo_manager.delete_airing(ep_path):
                raise RuntimeError("Tablo refused to delete the recording")
            delete_episode(ep_id)
            deleted_ids.append(ep_id)
        except Exception as e:
            errors.append(f"{ep.get('title')}: {e}")

    recalculate_show_stats(show_id)
    updated_show = get_show_by_id(show_id)

    return {
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "kept_protected": kept,
        "errors": errors,
        "show": updated_show
    }


@router.post("/mark_watched")
async def mark_show_watched(show_id: str = Query(...), watched: bool = Query(True)):
    """Mark every episode of a show watched (or unwatched) on the Tablo."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")
    body = json.dumps({"watched": True} if watched else {"watched": False, "position": 0})
    changed, errors = [], []
    for ep in get_episodes_by_show(show_id):
        if (ep.get("status") == "Watched") == watched:
            continue
        try:
            resp = await tablo_manager.request_recording("PATCH", ep["path"], body)
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"Tablo error {resp.status_code}")
            if not watched:
                set_episode_progress(ep["id"], position=0)
            set_episode_progress(ep["id"], watched=watched)
            changed.append(ep["id"])
        except Exception as e:
            errors.append(f"{ep.get('title')}: {e}")
    return {"changed_ids": changed, "errors": errors, "show": get_show_by_id(show_id)}


@router.post("/keep")
async def set_keep(req: KeepRequest, show_id: str = Query(...)):
    """Set the Tablo's keep rule for a recorded series: keep only the newest N recordings, or all.
    The Tablo itself then deletes older ones, even while TabloView isn't running."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")
    show = get_show_by_id(show_id)
    if not show or not (show.get("path") or "").startswith("/recordings/series/"):
        raise HTTPException(status_code=404, detail="Show not found")
    keep = {"rule": "count", "count": req.count} if req.count else {"rule": "none", "count": None}
    resp = await tablo_manager.request_local("PATCH", show["path"], json.dumps({"keep": keep}))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}: {resp.text[:120]}")
    try:
        echoed = resp.json().get("keep")
    except ValueError:
        echoed = None
    if echoed is not None and echoed.get("rule") != keep["rule"]:
        raise HTTPException(status_code=502, detail="The Tablo didn't accept the change")
    set_show_keep(show_id, echoed or keep)
    return {"success": True, "show": _with_rules(get_show_by_id(show_id))}


def _with_commercials(episodes: List[dict]) -> List[dict]:
    """Add each recording's commercial-finding status: done (with breaks), unreliable, failed,
    analyzing, or None (not looked at)."""
    from .. import dropouts
    found = get_commercials([e["id"] for e in episodes])
    current = commercials.status["current"]
    queued = set(commercials.queued_episodes())
    drops = {e["id"]: dropouts.get(e["id"]) for e in episodes}
    return [{**e, "commercials": (found[e["id"]]["status"] if e["id"] in found else "analyzing" if e["id"] == current
                                  else "queued" if e["id"] in queued else None),
             "commercial_breaks": len(found[e["id"]]["breaks"]) if e["id"] in found else 0,
             # Signal dropouts found (recordings the Tablo flagged as not clean; app/dropouts.py)
             "dropouts": (drops[e["id"]] or {}).get("spans", []),
             "finding_dropouts": dropouts.status["current"] == e["id"]} for e in episodes]


def _commercials_show_id(show_id: Optional[str], title: Optional[str]) -> str:
    """A show in the library by id, or a series by its title (from the guide): its recordings will get
    the id the sync gives them, so it can be turned on before anything has recorded."""
    if title and title.strip():
        return slugify_show_title(title.strip())
    if not show_id:
        raise HTTPException(status_code=400, detail="No show given")
    if not get_show_by_id(show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    return show_id


@router.get("/commercials")
async def get_commercials_setting(show_id: Optional[str] = None, title: Optional[str] = None):
    return {"on": _commercials_show_id(show_id, title) in commercials.enabled_shows()}


@router.post("/commercials")
async def set_commercials(req: CommercialsRequest, show_id: Optional[str] = None, title: Optional[str] = None):
    """Find commercial breaks in this show's recordings (in the background, on this PC)."""
    show_id = _commercials_show_id(show_id, title)
    commercials.set_show(show_id, req.on)
    show = get_show_by_id(show_id)
    return {"success": True, "show": _with_rules(show) if show else None,
            "waiting": len(commercials.pending()) if req.on else 0}


@router.post("/auto_export")
async def set_auto_export(req: AutoExportRequest, show_id: str = Query(...)):
    """Export this show's recordings to MP4 automatically, each once it has finished recording."""
    if not get_show_by_id(show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    waiting = autoexport.set_show(show_id, req.on, req.existing)
    return {"success": True, "show": _with_rules(get_show_by_id(show_id)), "waiting": waiting}


@router.post("/cleanup")
async def set_cleanup(req: CleanupRequest, show_id: str = Query(...)):
    """TabloView's automatic cleanup for a show: delete watched recordings N days after watching."""
    if not get_show_by_id(show_id):
        raise HTTPException(status_code=404, detail="Show not found")
    cleanup.set_rule(show_id, req.days)
    return {"success": True, "show": _with_rules(get_show_by_id(show_id))}


@router.get("/{show_id:path}")
async def get_show(show_id: str):
    show = get_show_by_id(show_id)
    if not show:
        # Also try with leading slash if omitted
        if not show_id.startswith("/"):
            show = get_show_by_id("/" + show_id)
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    episodes = get_episodes_by_show(show["id"])
    return {
        "show": _with_rules(show),
        "episodes": episodes
    }
