"""Tuner math for planned recordings: overlap conflicts and 'is it safe to watch live TV now?'."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _span(a: Dict[str, Any]):
    start = datetime.fromisoformat(str(a["air_datetime"]).replace("Z", "+00:00"))
    return start, start + timedelta(seconds=int(a.get("duration") or 0))


def find_conflicts(airings: List[Dict[str, Any]], tuners: int) -> List[Dict[str, Any]]:
    """Time windows where more recordings overlap than there are tuners.

    Marks each airing involved with 'conflict': True and returns
    [{'start', 'end', 'count', 'titles', 'paths'}], merged per continuous overloaded window.
    """
    if tuners <= 0:
        return []
    events = []
    for a in airings:
        a["conflict"] = False
        start, end = _span(a)
        events.append((start, 1, a))
        events.append((end, -1, a))
    # Ends before starts at the same instant: back-to-back shows don't overlap
    events.sort(key=lambda e: (e[0], e[1]))

    active: List[Dict[str, Any]] = []
    windows: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for when, kind, a in events:
        if kind == 1:
            active.append(a)
        else:
            active.remove(a)
        over = len(active) > tuners
        if over:
            if current is None:
                current = {"start": when, "end": when, "count": len(active), "airings": {}}
                windows.append(current)
            current["count"] = max(current["count"], len(active))
            for x in active:
                current["airings"][x["path"]] = x
                x["conflict"] = True
        elif current is not None:
            current["end"] = when
            current = None

    return [{
        "start": w["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": w["end"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": w["count"],
        "tuners": tuners,
        "titles": sorted({x["show_title"] for x in w["airings"].values()}),
        "paths": list(w["airings"].keys()),
    } for w in windows]


def peak_overlap(airings: List[Dict[str, Any]]) -> int:
    """Most recordings running at the same moment."""
    events = []
    for a in airings:
        start, end = _span(a)
        events += [(start, 1), (end, -1)]
    events.sort()
    cur = peak = 0
    for _, step in events:
        cur += step
        peak = max(peak, cur)
    return peak


def live_tv_check(upcoming: List[Dict[str, Any]], total: int, in_use: int, held: int,
                  horizon_minutes: int = 90) -> Dict[str, Any]:
    """Would tuning one more antenna channel now leave too few tuners for recordings that are about
    to start? Held tuners (closed streams the Tablo hasn't released yet) count as busy."""
    now = datetime.now(timezone.utc)
    soon = []
    for a in upcoming:
        start, end = _span(a)
        if now < start <= now + timedelta(minutes=horizon_minutes):
            soon.append(a)
    needed = peak_overlap(soon)
    free_after = total - in_use - 1
    return {
        "total": total,
        "in_use": in_use,
        "held": held,
        "free_after_tuning": max(free_after, 0),
        "recordings_soon": [{"title": a["show_title"], "start": a["air_datetime"],
                             "channel": a.get("channel_call_sign")} for a in soon],
        "needed": needed,
        "warn": total > 0 and needed > 0 and free_after < needed,
        "no_free_tuner": total > 0 and total - in_use <= 0,
    }
