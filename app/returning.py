"""Shows you used to record that are coming back: a season premiere (or a new episode 1) is in the guide
for a series you've had recordings of, but no recording rule is set for it.

"Used to record" is remembered in sync_meta "recorded_series" (guide series paths), added to after each
library sync, so a series still counts after all its recordings are deleted. Each return is announced
once per series and season (sync_meta "notified_returns").
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from .database import get_connection, get_guide_shows, get_sync_meta, set_sync_meta


def _load(key: str) -> set:
    try:
        return set(json.loads(get_sync_meta(key) or "[]"))
    except ValueError:
        return set()


def remember_recorded() -> set:
    """Add the guide series of everything in the library to what's been recorded before."""
    known = _load("recorded_series")
    with get_connection() as conn:
        for (raw,) in conn.execute("SELECT raw_json FROM shows"):
            try:
                path = (json.loads(raw or "{}") or {}).get("guide_path")
            except ValueError:
                continue
            if path:
                known.add(path)
    set_sync_meta("recorded_series", json.dumps(sorted(known)))
    return known


def find() -> List[Dict[str, Any]]:
    """Guide shows (same fields as the guide's) with an upcoming premiere, recorded before, no rule now."""
    known = _load("recorded_series")
    if not known:
        return []
    shows = [g for g in get_guide_shows(highlight="premieres", sort_by="soonest", limit=500)
             if g["path"] in known and (g.get("schedule_rule") or "none") == "none"]
    with get_connection() as conn:
        for g in shows:
            # The premiere itself (reruns may come before it), for the notice and once-per-season
            row = conn.execute("""
                SELECT air_datetime, season_number FROM guide_airings
                WHERE series_path = ? AND is_premiere = 1 AND datetime(air_datetime) > datetime('now')
                ORDER BY air_datetime LIMIT 1
            """, (g["path"],)).fetchone()
            g["premiere_at"] = row["air_datetime"] if row else g.get("next_air_datetime")
            g["premiere_season"] = row["season_number"] if row else g.get("next_season_number")
    return shows


def check() -> List[Dict[str, Any]]:
    """After a guide sync: announce returns not announced yet. Never raises."""
    from .notifications import send
    try:
        remember_recorded()
        returning = find()
        seen = _load("notified_returns")
        keys = {f"{g['path']}|{g.get('premiere_season') or g.get('premiere_at') or ''}": g for g in returning}
        new = [g for k, g in keys.items() if k not in seen]
        set_sync_meta("notified_returns", json.dumps(sorted(seen | set(keys))))
        for g in new[:3]:
            when = ""
            if g.get("premiere_at"):
                try:
                    when = " " + datetime.fromisoformat(g["premiere_at"].replace("Z", "+00:00")).astimezone().strftime("%a %b %d at %I:%M %p").replace(" 0", " ")
                except ValueError:
                    pass
            send("A show you recorded is back", f"{g['title']} has a season premiere{when}. Open TabloView to record it.")
        return new
    except Exception as e:
        print(f"[Returning] {e}")
        return []
