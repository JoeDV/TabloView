"""Watch list: recordings from any show, played one after another. When one is watched to the end
it comes off the list, and with "delete each after I finish it" it's deleted from the Tablo too,
unless it's protected there."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import (
    add_to_watch_list,
    get_episode_by_id,
    get_watch_list,
    remove_from_watch_list,
    set_watch_list,
)
from .episodes import delete_single_episode

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class EpisodeIds(BaseModel):
    episode_ids: List[str]


class Finished(BaseModel):
    delete: bool = False


@router.get("")
async def watch_list():
    episodes = get_watch_list()
    return {"count": len(episodes), "episodes": episodes}


@router.post("")
async def add(req: EpisodeIds):
    added = add_to_watch_list(req.episode_ids)
    return {"added": added, "count": len(get_watch_list())}


@router.put("")
async def reorder(req: EpisodeIds):
    """The whole list in its new order (moving one, removing some)."""
    set_watch_list(req.episode_ids)
    return {"count": len(get_watch_list())}


@router.delete("/{episode_id}")
async def remove(episode_id: str):
    remove_from_watch_list(episode_id)
    return {"count": len(get_watch_list())}


@router.post("/{episode_id}/finished")
async def finished(episode_id: str, req: Finished):
    """Called when a recording played from a run was watched to the end: it leaves the Watch list,
    and is deleted from the Tablo if asked, never when it's protected there."""
    remove_from_watch_list(episode_id)
    ep = get_episode_by_id(episode_id)
    if not req.delete or not ep:
        return {"deleted": False, "protected": False}
    if ep.get("protected"):
        return {"deleted": False, "protected": True}
    try:
        res = await delete_single_episode(episode_id)
    except HTTPException as e:
        return {"deleted": False, "protected": False, "error": e.detail}
    return {"deleted": True, "protected": False, "show": res.get("show")}
