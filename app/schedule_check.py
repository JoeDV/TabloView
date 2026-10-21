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


def same_episode(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Two airings of the same episode: same series and season/episode numbers, or (without numbers)
    the same episode title. Shows without either (news, live events) never match."""
    if a.get("series_path") != b.get("series_path") or a.get("path") == b.get("path"):
        return False
    if (a.get("season_number") or 0) > 0 and (a.get("episode_number") or 0) > 0:
        return (a.get("season_number"), a.get("episode_number")) == (b.get("season_number"), b.get("episode_number"))
    title = (a.get("episode_title") or "").strip().lower()
    return bool(title) and title == (b.get("episode_title") or "").strip().lower()


def find_alternatives(scheduled: List[Dict[str, Any]], candidates: List[Dict[str, Any]],
                      tuners: int) -> List[Dict[str, Any]]:
    """For each conflict, the recordings involved and other airings of the same episodes.

    scheduled: everything the Tablo will record (upcoming); candidates: future airings of those series,
    scheduled or not. An alternative 'resolves' the conflict when recording it instead leaves that
    time within the tuners and doesn't create a new conflict of its own."""
    now = datetime.now(timezone.utc)
    conflicts = find_conflicts([dict(a) for a in scheduled], tuners)
    by_path = {a["path"]: a for a in scheduled}
    result = []
    for c in conflicts:
        items = []
        for path in c["paths"]:
            a = by_path[path]
            alts = []
            for cand in candidates:
                if cand.get("schedule_state") == "scheduled" or not same_episode(a, cand):
                    continue
                start, _ = _span(cand)
                if start <= now:
                    continue
                trial = [dict(x) for x in scheduled if x["path"] != path] + [dict(cand)]
                after = find_conflicts(trial, tuners)
                resolves = not any(cand["path"] in w["paths"] for w in after) and \
                    not any(w["start"] < c["end"] and w["end"] > c["start"] for w in after)
                alts.append({**{k: cand.get(k) for k in ("path", "air_datetime", "duration", "channel_call_sign",
                                                         "channel_network")}, "resolves": resolves})
            alts.sort(key=lambda x: (not x["resolves"], x["air_datetime"]))
            items.append({**{k: a.get(k) for k in ("path", "series_path", "show_title", "episode_title", "season_number",
                                                   "episode_number", "air_datetime", "duration", "channel_call_sign")},
                          "alternatives": alts[:5]})
        result.append({**{k: c[k] for k in ("start", "end", "count", "tuners", "titles")}, "recordings": items})
    return result


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


def _channel(a: Dict[str, Any]) -> str:
    return a.get("channel_identifier") or a.get("channel_call_sign") or a.get("path") or ""


def live_tv_check(upcoming: List[Dict[str, Any]], total: int, in_use: int, held: int,
                  recording: Optional[int] = None, horizon_minutes: int = 90) -> Dict[str, Any]:
    """Would tuning one more antenna channel now leave too few tuners for recordings that are about
    to start? Checked at each moment a recording starts: the recordings running then (one tuner per
    channel), plus the tuners busy with anything else now (live TV, or held after a stream closed:
    counted as still busy), plus the new channel.

    A recording that follows another on the same channel takes over its tuner: two recordings
    running and two more starting on the same two channels need two tuners, not four (a 4-tuner
    Tablo warned "Not enough tuners" for any other channel)."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=horizon_minutes)
    spans = [(a, *_span(a)) for a in upcoming]
    soon = [a for a, start, _ in spans if now < start <= horizon]

    def channels_recording(t: datetime) -> int:
        return len({_channel(a) for a, start, end in spans if start <= t < end})

    recording_now = max(channels_recording(now), recording or 0)
    other = max(in_use - recording_now, 0)  # live TV and held tuners
    worst = recording_now + other + 1
    for a in soon:
        worst = max(worst, channels_recording(_span(a)[0]) + other + 1)
    return {
        "total": total,
        "in_use": in_use,
        "held": held,
        "free_after_tuning": max(total - in_use - 1, 0),
        "recordings_soon": [{"title": a["show_title"], "start": a["air_datetime"],
                             "channel": a.get("channel_call_sign")} for a in soon],
        "needed": max(worst - other - 1, 0),
        "warn": total > 0 and bool(soon) and worst > total,
        "no_free_tuner": total > 0 and total - in_use <= 0,
    }
