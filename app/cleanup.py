"""Automatic cleanup: per show, delete watched recordings a set number of days after they were watched.
Protected recordings are never deleted. The Tablo doesn't record when something was watched, so
TabloView notes the first sync that sees each recording as watched (sync_meta "watched_since").
Recordings already watched when this is first tracked count from then. Runs after each library sync."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import (
    get_watched_episodes, get_sync_meta, set_sync_meta, delete_episode, recalculate_show_stats,
)
from .settings import load_settings, save_settings

DAY_CHOICES = (1, 3, 7, 14, 30)


def rules() -> Dict[str, int]:
    """show_id -> days after watching."""
    return {k: int(v) for k, v in (load_settings().get("cleanup_days") or {}).items() if v}


def set_rule(show_id: str, days: Optional[int]) -> Dict[str, int]:
    current = rules()
    if days:
        current[show_id] = int(days)
    else:
        current.pop(show_id, None)
    save_settings({"cleanup_days": current})
    return current


def _watched_since() -> Dict[str, str]:
    try:
        return json.loads(get_sync_meta("watched_since") or "{}")
    except ValueError:
        return {}


def track_watched(watched: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, str]:
    """Remember when each recording was first seen watched; forget ones no longer watched or gone."""
    now = now or datetime.now(timezone.utc)
    known = _watched_since()
    since = {ep["id"]: known.get(ep["id"]) or now.isoformat() for ep in watched}
    set_sync_meta("watched_since", json.dumps(since))
    return since


def due(watched: List[Dict[str, Any]], since: Dict[str, str], show_rules: Dict[str, int],
        now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Watched, unprotected recordings past their show's limit."""
    now = now or datetime.now(timezone.utc)
    result = []
    for ep in watched:
        days = show_rules.get(ep["show_id"])
        if not days or ep.get("protected") or ep["id"] not in since:
            continue
        if now - datetime.fromisoformat(since[ep["id"]]) >= timedelta(days=days):
            result.append(ep)
    return result


async def run() -> int:
    """After a library sync: delete what's due. Returns how many were deleted. Never raises."""
    from .tablo_client import tablo_manager
    from .notifications import send
    try:
        watched = get_watched_episodes()
        since = track_watched(watched)
        targets = due(watched, since, rules())
        deleted, shows = [], set()
        for ep in targets:
            try:
                if await tablo_manager.delete_airing(ep["path"]):
                    delete_episode(ep["id"])
                    deleted.append(ep)
                    shows.add(ep["show_id"])
            except Exception as e:
                print(f"[Cleanup] Couldn't delete {ep.get('show_title')} {ep.get('title')}: {e}")
        for show_id in shows:
            recalculate_show_stats(show_id)
        if deleted:
            print(f"[Cleanup] Deleted {len(deleted)} watched recordings")
            titles = sorted({ep["show_title"] for ep in deleted})
            send("Cleaned up recordings",
                 f"Deleted {len(deleted)} watched recording{'s' if len(deleted) != 1 else ''} "
                 f"({', '.join(titles[:3])}{' and more' if len(titles) > 3 else ''}).")
        return len(deleted)
    except Exception as e:
        print(f"[Cleanup] {e}")
        return 0
