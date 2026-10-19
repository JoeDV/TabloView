"""Guide search, discovery, and series recording management routes."""

import json
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from ..database import (
    get_guide_shows,
    get_scheduled_guide_shows,
    get_guide_show_by_path,
    update_guide_show_schedule,
    get_guide_highlight_counts,
    update_airing_schedule_states,
    get_upcoming_recordings,
    get_series_airings,
)
from ..schedule_check import find_conflicts, find_alternatives
from ..tablo_client import tablo_manager
from ..sync_service import sync_service, extract_image_url
from .live import pick_logo

router = APIRouter(prefix="/api/guide", tags=["guide"])


class SeriesScheduleRequest(BaseModel):
    path: str
    rule: str  # "new", "all", "none"


class EpisodeScheduleRequest(BaseModel):
    path: str
    scheduled: bool


class SwapRequest(BaseModel):
    skip_path: str
    record_path: str


@router.get("/shows")
async def list_guide_shows(
    category: Optional[str] = Query(None, description="all, series, movies, sports"),
    search: Optional[str] = Query(None, description="Search term for title/synopsis"),
    rule: Optional[str] = Query(None, description="Filter: 'all', 'new', 'scheduled', 'unscheduled', 'none'"),
    highlight: Optional[str] = Query(None, description="Filter: 'primetime_new', 'premieres'"),
    sort: str = Query("title", description="Sort: 'title', 'scheduled', 'airings', 'recent', 'soonest', 'primetime', 'premieres'"),
    limit: int = Query(150, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Search and browse all broadcast guide series, movies, and sports with primetime and premiere discovery."""
    shows = get_guide_shows(
        category=category,
        search=search,
        rule=rule,
        highlight=highlight,
        sort_by=sort,
        limit=limit,
        offset=offset
    )
    scheduled_shows = get_scheduled_guide_shows()
    highlight_counts = get_guide_highlight_counts()
    return {
        "count": len(shows),
        "total_scheduled": len(scheduled_shows),
        "highlights": highlight_counts,
        "shows": shows
    }


@router.get("/upcoming")
async def upcoming_recordings():
    """Every airing the Tablo plans to record, soonest first, with times where more overlap than
    there are tuners ('conflicts'). Built from the cached guide; no extra requests to the Tablo
    beyond the (cached) tuner count."""
    from .live import model_tuner_count
    recordings = get_upcoming_recordings()
    tuners = (await model_tuner_count()) if tablo_manager.is_authenticated else None
    conflicts = find_conflicts(recordings, tuners) if tuners else []
    return {"tuners": tuners, "count": len(recordings), "recordings": recordings, "conflicts": conflicts}


@router.get("/returning")
async def returning_shows():
    """Series you've recorded before with a season premiere coming up and no recording rule now."""
    from .. import returning
    return {"shows": returning.find()}


@router.get("/conflicts")
async def conflict_alternatives():
    """Each recording conflict with the recordings involved and other airings of those same episodes
    (reruns, or the same network on another station) that could be recorded instead. From the cached
    guide; no requests to the Tablo beyond the (cached) tuner count."""
    from .live import model_tuner_count
    scheduled = get_upcoming_recordings()
    tuners = (await model_tuner_count()) if tablo_manager.is_authenticated else None
    if not tuners:
        return {"tuners": tuners, "conflicts": []}
    candidates = get_series_airings(sorted({a["series_path"] for a in scheduled if a.get("series_path")}))
    return {"tuners": tuners, "conflicts": find_alternatives(scheduled, candidates, tuners)}


async def _set_scheduled(path: str, scheduled: bool) -> None:
    path = path if path.startswith("/") else "/" + path
    resp = await tablo_manager.request_local("PATCH", path, json.dumps({"scheduled": scheduled}))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}: {resp.text[:120]}")
    update_airing_schedule_states({path: "scheduled" if scheduled else "none"})


@router.post("/conflicts/swap")
async def swap_recording(req: SwapRequest):
    """Record another airing of the same episode instead: schedule the new one first, then skip the
    original, so a failure never leaves the episode unrecorded."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")
    await _set_scheduled(req.record_path, True)
    try:
        await _set_scheduled(req.skip_path, False)
    except HTTPException as e:
        return {"success": False, "recorded": req.record_path, "error": f"Recorded the new time, but couldn't skip the original: {e.detail}"}
    return {"success": True, "recorded": req.record_path, "skipped": req.skip_path}


@router.get("/highlights")
async def get_highlights():
    """Return count of upcoming primetime new and season premiere shows."""
    return get_guide_highlight_counts()


@router.get("/scheduled")
async def list_scheduled_shows():
    """List all series currently configured with an active recording schedule."""
    scheduled = get_scheduled_guide_shows()
    return {
        "count": len(scheduled),
        "shows": scheduled
    }


@router.get("/series")
async def get_guide_series_details(path: str = Query(..., description="Guide series path, e.g. /guide/series/163949")):
    """Get single guide show details from database or live Tablo."""
    show = get_guide_show_by_path(path)
    if not show and tablo_manager.is_authenticated:
        try:
            resp = await tablo_manager.request_local("GET", path)
            if resp.status_code == 200:
                data = resp.json()
                info = data.get("series") or data
                return {
                    "path": path,
                    "title": info.get("title"),
                    "description": info.get("description"),
                    "genres": info.get("genres", []),
                    "schedule_rule": data.get("schedule_rule", "none"),
                    "cover_url": extract_image_url(info.get("cover_image")),
                    "backdrop_url": extract_image_url(info.get("background_image")),
                    "show_counts": data.get("show_counts", {}),
                    "raw_json": data
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Tablo hardware error: {e}")
    if not show:
        raise HTTPException(status_code=404, detail="Guide show not found")
    return show


async def refresh_series_airing_states(series_path: str, delay: float = 2.0):
    """After a series rule change the Tablo re-plans its schedule; re-read the record status of
    that series' upcoming airings so the Live TV grid badges are right without a full guide sync."""
    await asyncio.sleep(delay)
    try:
        resp = await tablo_manager.request_local("GET", f"{series_path}/episodes")
        if resp.status_code != 200 or not isinstance(resp.json(), list):
            return
        sem = asyncio.Semaphore(15)

        async def read_state(p: str):
            async with sem:
                r = await tablo_manager.request_local("GET", p)
                if r.status_code == 200:
                    return p, (r.json().get("schedule") or {}).get("state") or "none"
            return None

        results = await asyncio.gather(*[read_state(p) for p in resp.json()], return_exceptions=True)
        update_airing_schedule_states(dict(x for x in results if isinstance(x, tuple)))
    except Exception as e:
        print(f"[Guide] Couldn't refresh record status for {series_path}: {e}")


@router.post("/series/schedule")
async def set_series_schedule(payload: SeriesScheduleRequest):
    """Set or cancel series recording schedule rule ('new', 'all', or 'none')."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")

    rule = payload.rule.lower()
    if rule not in ("new", "all", "none"):
        raise HTTPException(status_code=400, detail="Invalid rule. Must be 'new', 'all', or 'none'")

    path = payload.path if payload.path.startswith("/") else "/" + payload.path

    # Send signed PATCH to local Tablo hardware
    patch_body = json.dumps({
        "schedule": {
            "rule": rule
        }
    })

    try:
        resp = await tablo_manager.request_local("PATCH", path, patch_body)
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Tablo error: {resp.text[:120]}"
            )

        # Update local SQLite cache, then re-read which airings the Tablo now plans to record
        update_guide_show_schedule(path, rule)
        asyncio.create_task(refresh_series_airing_states(path))
        updated = get_guide_show_by_path(path)

        return {
            "success": True,
            "path": path,
            "rule": rule,
            "show": updated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update schedule: {e}")


@router.get("/series/episodes")
async def get_series_upcoming_episodes(series_path: str = Query(...)):
    """Fetch upcoming broadcast airings/episodes for a series directly from Tablo DVR."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")

    if not series_path.startswith("/"):
        series_path = "/" + series_path

    episodes_endpoint = f"{series_path}/episodes"

    try:
        resp = await tablo_manager.request_local("GET", episodes_endpoint)
        if resp.status_code == 404:
            return {"series_path": series_path, "count": 0, "episodes": []}
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Tablo error: {resp.text[:100]}")

        ep_paths = resp.json()
        if not isinstance(ep_paths, list):
            return {"series_path": series_path, "count": 0, "episodes": []}

        # Fetch detailed info for each upcoming episode
        sem = asyncio.Semaphore(15)

        async def fetch_ep(p: str):
            async with sem:
                try:
                    r = await tablo_manager.request_local("GET", p)
                    if r.status_code == 200:
                        d = r.json()
                        ad = d.get("airing_details", {})
                        ep = d.get("episode", {})
                        ch_info = ad.get("channel", {}).get("channel", {})
                        sched = d.get("schedule", {})

                        # Channel logo
                        logo_url = pick_logo(ch_info.get("logos", []))

                        season_num = ep.get("season_number") or 0
                        ep_num = ep.get("number") or ep.get("episode_number") or 0
                        ep_title = ep.get("title")
                        if not ep_title:
                            if ep_num:
                                ep_title = f"Episode {ep_num}"
                            else:
                                ep_title = ad.get("show_title") or "Episode"

                        return {
                            "path": p,
                            "object_id": d.get("object_id"),
                            "series_path": d.get("series_path"),
                            "title": ep_title,
                            "description": ep.get("description") or "",
                            "season_number": season_num,
                            "episode_number": ep_num,
                            "orig_air_date": ep.get("orig_air_date", ""),
                            "air_datetime": ad.get("datetime", ""),
                            "duration": ad.get("duration", 0),
                            "channel": {
                                "call_sign": ch_info.get("call_sign") or ch_info.get("name") or "",
                                "major": ch_info.get("major"),
                                "minor": ch_info.get("minor"),
                                "network": ch_info.get("network") or "",
                                "logo_url": logo_url
                            },
                            "qualifiers": d.get("qualifiers", []),
                            "is_scheduled": sched.get("state") in ("scheduled", "set"),
                            "schedule_state": sched.get("state", "none"),
                            "schedule_qualifier": sched.get("qualifier", "none"),
                        }
                except Exception:
                    pass
                return None

        episodes = await asyncio.gather(*[fetch_ep(p) for p in ep_paths])
        valid_episodes = [e for e in episodes if e]

        # Sort by air date
        valid_episodes.sort(key=lambda x: x.get("air_datetime") or "")

        return {
            "series_path": series_path,
            "count": len(valid_episodes),
            "episodes": valid_episodes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching upcoming airings: {e}")


@router.post("/episodes/schedule")
async def set_episode_schedule(payload: EpisodeScheduleRequest):
    """Toggle individual upcoming episode recording schedule on/off."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")

    path = payload.path if payload.path.startswith("/") else "/" + payload.path
    patch_body = json.dumps({"scheduled": payload.scheduled})

    try:
        resp = await tablo_manager.request_local("PATCH", path, patch_body)
        if resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Tablo error: {resp.text[:120]}"
            )
        update_airing_schedule_states({path: "scheduled" if payload.scheduled else "none"})
        return {
            "success": True,
            "path": path,
            "scheduled": payload.scheduled
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle episode recording: {e}")


@router.post("/sync")
async def trigger_guide_sync():
    """Trigger background sync of OTA guide series, movies, and sports."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")

    asyncio.create_task(sync_service.sync_guide())
    return {"status": "sync_started", "message": "OTA Guide sync running in background"}
