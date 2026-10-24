"""Developer tools, only when the server is started with TABLOVIEW_DEV_TOOLS=1 (never in the app people
use): /dev/marks, a player for marking where commercial breaks really start and end, to check the
commercial finder against (app/commercials.py). Marks are kept in data/ad_marks/<episode id>.json."""

import json
import os
import re
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import BASE_DIR, DATA_DIR
from ..database import get_commercials, get_connection

ENABLED = os.getenv("TABLOVIEW_DEV_TOOLS") == "1"
MARKS_DIR = DATA_DIR / "ad_marks"
PAGE = BASE_DIR / "tools" / "marks.html"

router = APIRouter(tags=["devtools"])


class Mark(BaseModel):
    t: float = Field(ge=0)
    kind: str = Field(pattern="^(start|end)$")  # a break starts / the show's back


class Marks(BaseModel):
    marks: List[Mark] = Field(default_factory=list, max_length=200)
    note: str = Field(default="", max_length=2000)


def _marks_file(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", episode_id):
        raise HTTPException(status_code=404, detail="No such recording")
    return MARKS_DIR / f"{episode_id}.json"


@router.get("/dev/marks")
async def marks_page():
    return FileResponse(str(PAGE), headers={"Cache-Control": "no-cache"})


@router.get("/api/dev/recordings")
async def recordings():
    """Every finished recording, with the breaks the finder found and any marks."""
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, show_title, title, season_number, episode_number, air_date, duration, channel_name, network "
            "FROM episodes ORDER BY show_title, air_date DESC").fetchall()]
    found = get_commercials([r["id"] for r in rows])
    for r in rows:
        c = found.get(r["id"]) or {}
        r["found"] = c.get("breaks") or []
        r["found_status"] = c.get("status")
        f = MARKS_DIR / f"{r['id']}.json"
        r["marks"] = json.loads(f.read_text(encoding="utf-8")).get("marks", []) if f.exists() else []
    return {"recordings": rows}


@router.get("/api/dev/marks/{episode_id}")
async def get_marks(episode_id: str):
    f = _marks_file(episode_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"marks": [], "note": ""}


@router.put("/api/dev/marks/{episode_id}")
async def save_marks(episode_id: str, body: Marks):
    f = _marks_file(episode_id)
    MARKS_DIR.mkdir(parents=True, exist_ok=True)
    data = {"marks": sorted((m.model_dump() for m in body.marks), key=lambda m: m["t"]), "note": body.note}
    f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data
