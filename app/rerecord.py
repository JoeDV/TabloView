"""Record a failed or partial recording again: find upcoming airings of the same episode (reruns, or the
same network on another station) and, automatically after each sync (setting "rerecord_failed"),
schedule the earliest one that doesn't cause a tuner conflict. Each failed recording is handled once
(sync_meta "rerecorded")."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import (
    get_connection, get_series_airings, get_upcoming_recordings, get_sync_meta, set_sync_meta,
    recording_details, update_airing_schedule_states,
)
from .schedule_check import find_conflicts, same_episode
from .settings import load_settings

# Only failures this recent are re-recorded automatically (older ones may not matter any more)
RECENT_DAYS = 14
# The library and guide syncs can both finish at once; one check at a time
_lock = asyncio.Lock()


def _recordings() -> List[Dict[str, Any]]:
    """Every recording with what's needed to match it to the guide."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.id, e.show_id, e.show_title, e.season_number, e.episode_number, e.air_date, e.duration,
                   e.raw_json, s.raw_json AS show_raw
            FROM episodes e LEFT JOIN shows s ON s.id = e.show_id
        """).fetchall()
    result = []
    for r in rows:
        try:
            raw = json.loads(r["raw_json"] or "{}")
            show_raw = json.loads(r["show_raw"] or "{}")
        except ValueError:
            continue
        result.append({
            "id": r["id"], "show_id": r["show_id"], "show_title": r["show_title"], "air_date": r["air_date"],
            "duration": r["duration"],
            # In the guide's terms, so same_episode() can compare it with guide airings
            "series_path": show_raw.get("guide_path"),
            "season_number": r["season_number"], "episode_number": r["episode_number"],
            "episode_title": (raw.get("episode") or {}).get("title") or "",
            **recording_details(raw),
        })
    return result


def alternatives(episode_id: str) -> Optional[Dict[str, Any]]:
    """Upcoming airings of the same episode as this recording, soonest first."""
    rec = next((r for r in _recordings() if r["id"] == episode_id), None)
    if not rec:
        return None
    airings = [a for a in get_series_airings([rec["series_path"]]) if same_episode({**rec, "path": None}, a)] \
        if rec["series_path"] else []
    return {"recording": rec, "airings": airings}


def _fits(airing: Dict[str, Any], tuners: Optional[int]) -> bool:
    """Recording this airing too wouldn't need more tuners than the Tablo has."""
    if not tuners:
        return False
    planned = get_upcoming_recordings() + [{**airing, "schedule_state": "scheduled"}]
    return not any(airing["path"] in c["paths"] for c in find_conflicts(planned, tuners))


def pick(recs: List[Dict[str, Any]], handled: Dict[str, str], tuners: Optional[int],
         now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """[{recording, airing}] to schedule: recent failures not handled yet, with no complete copy in the
    library and no airing of that episode already set to record, using the earliest that fits."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)
    plans = []
    for rec in recs:
        if not rec["incomplete"] or rec["id"] in handled or not rec["series_path"]:
            continue
        try:
            if datetime.fromisoformat(rec["air_date"].replace("Z", "+00:00")) < cutoff:
                continue
        except (AttributeError, ValueError):
            continue
        twin = {**rec, "path": None}
        if any(o["id"] != rec["id"] and not o["incomplete"] and same_episode(twin, {**o, "path": o["id"]})
               for o in recs):
            continue
        airings = sorted((a for a in get_series_airings([rec["series_path"]]) if same_episode(twin, a)),
                         key=lambda a: a["air_datetime"])
        if any(a.get("schedule_state") == "scheduled" for a in airings):
            continue
        choice = next((a for a in airings if _fits(a, tuners)), None)
        if choice:
            plans.append({"recording": rec, "airing": choice})
    return plans


async def run() -> List[Dict[str, Any]]:
    """After a sync: schedule reruns of recent failed recordings (if the setting is on). Never raises."""
    from .notifications import send
    from .tablo_client import tablo_manager
    from .routes.live import model_tuner_count
    if not load_settings().get("rerecord_failed", True):
        return []
    async with _lock:
        return await _run(send, tablo_manager, model_tuner_count)


async def _run(send, tablo_manager, model_tuner_count) -> List[Dict[str, Any]]:
    try:
        handled = json.loads(get_sync_meta("rerecorded") or "{}")
        done = []
        for plan in pick(_recordings(), handled, await model_tuner_count()):
            rec, airing = plan["recording"], plan["airing"]
            resp = await tablo_manager.request_local("PATCH", airing["path"], json.dumps({"scheduled": True}))
            if resp.status_code not in (200, 204):
                print(f"[Rerecord] The Tablo refused to schedule {airing['path']}: HTTP {resp.status_code}")
                continue
            update_airing_schedule_states({airing["path"]: "scheduled"})
            handled[rec["id"]] = airing["path"]
            done.append(plan)
            print(f"[Rerecord] {rec['show_title']} {rec['episode_title']}: recording again at {airing['air_datetime']}")
        if done:
            set_sync_meta("rerecorded", json.dumps(handled))
            for plan in done[:3]:
                rec, airing = plan["recording"], plan["airing"]
                when = datetime.fromisoformat(airing["air_datetime"].replace("Z", "+00:00")).astimezone()
                se = f" S{rec['season_number']}E{rec['episode_number']}" if rec["season_number"] and rec["episode_number"] else ""
                send("Recording again", f"{rec['show_title']}{se} didn't record completely, so TabloView set it to "
                     f"record again {when.strftime('%a %b %d at %I:%M %p').replace(' 0', ' ')} "
                     f"({airing.get('channel_call_sign') or 'another airing'}).")
        return done
    except Exception as e:
        print(f"[Rerecord] {e}")
        return []
