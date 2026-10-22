"""The Guide's Streaming tab: shows on streaming (FAST) channels over the next week, by category."""

import asyncio
import json
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import streaming
from ..tablo_client import tablo_manager
from .live import pick_logo

router = APIRouter(prefix="/api/streaming", tags=["streaming"])

AIRING_ID = re.compile(r"^LH-[A-Za-z0-9_-]+$")


class RecordRequest(BaseModel):
    airing_id: str
    scheduled: bool = True


# The Tablo only knows /guide/LH-... objects when the request ends in ?lh, as Tablo's app sends it
# ("Endpoint not found" otherwise). The signature still covers the bare path.
LH = "?lh"


async def schedule_states(airing_ids):
    """Each airing's record status on the Tablo ('scheduled', 'none', ...): streaming airings are
    Tablo objects at /guide/<the cloud guide's airing ID>, read 50 at a time."""
    if not airing_ids or not tablo_manager.is_authenticated:
        return {}
    states = {}
    paths = [f"/guide/{i}" for i in airing_ids]
    for n in range(0, len(paths), 50):
        try:
            resp = await tablo_manager.request_local("POST", "/batch" + LH, json.dumps(paths[n:n + 50]))
            found = resp.json() if resp.status_code == 200 else {}
        except Exception:
            found = {}
        for p, o in (found.items() if isinstance(found, dict) else []):
            if isinstance(o, dict) and "schedule" in o:
                states[p[len("/guide/"):]] = (o.get("schedule") or {}).get("state") or "none"
    return states


@router.get("/shows")
async def streaming_shows(q: Optional[str] = Query(None), category: str = Query("all"),
                          recordable: bool = Query(False)):
    """Shows with an airing still to come, soonest first (on now at the top), with how many are in
    each category. Loads the listings first if TabloView has none yet."""
    if not streaming.last_refresh() and tablo_manager.is_authenticated and not streaming.status["refreshing"]:
        asyncio.create_task(streaming.refresh())
    all_shows = await asyncio.to_thread(streaming.shows)
    pool = [s for s in all_shows if not recordable or s["can_record"]]
    if q and q.strip():
        needle = q.strip().lower()
        pool = [s for s in pool if needle in s["title"].lower()]
    counts = {c: 0 for c in streaming.ORDER}
    for s in pool:
        counts[s["category"]] += 1
    picked = pool if category == "all" else [s for s in pool if s["category"] == category]
    out = []
    for s in picked[:300]:
        n = s["next_airing"]
        out.append({**s, "next_airing": {**{k: v for k, v in n.items() if k != "logos"},
                                         "channel_logo": pick_logo(n["logos"])}})
    return {
        "loading": streaming.status["refreshing"] or (not streaming.last_refresh() and tablo_manager.is_authenticated),
        "error": streaming.status["error"],
        "refreshed": streaming.last_refresh(),
        "total": len(pool),
        "categories": [{"id": c, "label": streaming.LABELS[c], "count": counts[c]} for c in streaming.ORDER if counts[c]],
        "shows": out,
    }


@router.get("/shows/{show_id}/airings")
async def show_airings(show_id: str):
    """Every upcoming airing of one show on the streaming channels."""
    airings = await asyncio.to_thread(streaming.airings_for, show_id)
    states = await schedule_states([a["id"] for a in airings[:40] if a["can_record"]])
    return {"airings": [{
        "id": a["id"], "title": a["title"], "show_title": a["show_title"], "kind": a["kind"],
        "season_number": a["season_number"], "episode_number": a["episode_number"],
        "air_datetime": a["air_datetime"], "duration": a["duration"], "description": a["description"],
        "image": a["image"], "tags": json.loads(a["tags"] or "[]"),
        "channel_identifier": a["channel_identifier"], "channel_name": a["channel_name"],
        "channel_logo": pick_logo(json.loads(a["channel_logos"] or "[]")), "can_record": bool(a["can_record"]),
        "schedule_state": states.get(a["id"]),
    } for a in airings]}


@router.post("/record")
async def record_airing(req: RecordRequest):
    """Record (or stop recording) a streaming airing on the Tablo: the same request as for antenna
    airings, sent to /guide/<the airing's cloud guide ID> (seen from Tablo's own app, 2026-10-21).
    Only airings in TabloView's streaming listings, on channels the Tablo may record."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")
    if not AIRING_ID.match(req.airing_id):
        raise HTTPException(status_code=400, detail="Not a streaming airing")
    airing = await asyncio.to_thread(streaming.airing, req.airing_id)
    if not airing:
        raise HTTPException(status_code=404, detail="That airing isn't in the streaming guide")
    if req.scheduled and not airing["can_record"]:
        raise HTTPException(status_code=400, detail=f"Your Tablo isn't allowed to record {airing['channel_name']}")
    path = f"/guide/{req.airing_id}{LH}"
    resp = await tablo_manager.request_local("PATCH", path, json.dumps({"scheduled": req.scheduled}))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}: {resp.text[:120]}")
    streaming.forget_upcoming()  # Live TV's "Rec" marks
    state = (await schedule_states([req.airing_id])).get(req.airing_id)
    return {"airing_id": req.airing_id, "schedule_state": state}
