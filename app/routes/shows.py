"""Show catalog and episode listing routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from ..database import (
    get_shows,
    get_show_by_id,
    get_episodes_by_show,
    delete_episode,
    recalculate_show_stats
)
from ..tablo_client import tablo_manager

router = APIRouter(prefix="/api/shows", tags=["shows"])


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
    episodes = get_episodes_by_show(show_id)
    return {
        "show": show,
        "show_id": show_id,
        "show_title": show["title"],
        "count": len(episodes),
        "episodes": episodes
    }


@router.post("/delete_watched")
async def delete_watched_query(show_id: str = Query(...)):
    """Delete all watched episodes for this show."""
    episodes = get_episodes_by_show(show_id)
    watched = [ep for ep in episodes if ep.get("status") == "Watched"]

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
        "errors": errors,
        "show": updated_show
    }


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
        "show": show,
        "episodes": episodes
    }
