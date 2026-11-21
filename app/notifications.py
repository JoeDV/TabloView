"""Windows notifications (shown by the tray icon) when a recording goes wrong, upcoming recordings
conflict, or the Tablo's drive is almost full. Each problem is announced once: what's been announced is remembered in sync_meta.
Running from source there's no tray icon, so nothing is shown."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .database import get_incomplete_recordings, get_storage_by_show, get_sync_meta, set_sync_meta, get_upcoming_recordings
from .schedule_check import find_conflicts
from .settings import load_settings

CONFLICT_HORIZON_HOURS = 48
# The Tablo's drive: "almost full" from 90% used, said again at 95%; once it's back under 85% the
# next time it fills is announced again
SPACE_LEVELS = (90, 95)
SPACE_REARM = 85

_notifier: Optional[Callable[[str, str], None]] = None


def set_notifier(fn: Optional[Callable[[str, str], None]]) -> None:
    """The launcher registers the tray icon's notify(title, message) here."""
    global _notifier
    _notifier = fn


def available() -> bool:
    """True in the desktop app (it has a tray icon to show notifications from)."""
    return _notifier is not None


def send(title: str, message: str) -> None:
    if not _notifier or not load_settings().get("notifications", True):
        return
    try:
        _notifier(title, message)
    except Exception as e:
        print(f"[Notify] Couldn't show a notification: {e}")


def _load(key: str) -> Optional[set]:
    raw = get_sync_meta(key)
    try:
        return set(json.loads(raw)) if raw else None
    except ValueError:
        return None


def _label(ep: Dict[str, Any]) -> str:
    s, e = ep.get("season_number") or 0, ep.get("episode_number") or 0
    return f"{ep.get('show_title')} S{s}E{e}" if s and e else f"{ep.get('show_title')}: {ep.get('title')}"


def describe_problem(ep: Dict[str, Any]) -> str:
    """Same wording as the episode list's status tags."""
    actual, scheduled = ep.get("actual_duration") or 0, ep.get("duration") or 0
    if ep.get("recording_state") == "failed":
        if scheduled and actual >= scheduled - 60:
            return "the Tablo lost signal during the recording"
        if actual > 0:
            return f"the recording stopped after {round(actual / 60)} minutes (signal lost)"
        return "the recording failed"
    return f"the recording stopped {round((ep.get('ended_early') or 0) / 60)} minutes early"


def check_recordings() -> List[Dict[str, Any]]:
    """After a library sync: announce recordings that newly failed or came out short.
    The first time (nothing remembered yet), existing problems are remembered, not announced."""
    problems = get_incomplete_recordings()
    current = {p["id"] for p in problems}
    seen = _load("notified_recordings")
    new = [] if seen is None else [p for p in problems if p["id"] not in seen]
    # Only keep recordings that still exist, so the list doesn't grow forever
    set_sync_meta("notified_recordings", json.dumps(sorted(current)))
    if len(new) == 1:
        send("Recording problem", f"{_label(new[0])}: {describe_problem(new[0])}.")
    elif new:
        names = ", ".join(_label(p) for p in new[:3]) + (f" and {len(new) - 3} more" if len(new) > 3 else "")
        send("Recording problems", f"{len(new)} recordings didn't record completely: {names}.")
    return new


def _when(iso: str) -> str:
    local = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    today = datetime.now().astimezone().date()
    day = "today" if local.date() == today else "tomorrow" if local.date() == today + timedelta(days=1) else local.strftime("%A")
    return f"{day} at {local.strftime('%I:%M %p').lstrip('0')}"


def check_conflicts(tuners: Optional[int]) -> List[Dict[str, Any]]:
    """Announce recording conflicts in the next CONFLICT_HORIZON_HOURS that haven't been announced."""
    if not tuners:
        return []
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=CONFLICT_HORIZON_HOURS)
    # Conflicted airings included: they're the recordings that won't happen
    soon = [c for c in find_conflicts(get_upcoming_recordings(include_conflicted=True), tuners)
            if now < datetime.fromisoformat(c["start"].replace("Z", "+00:00")) <= horizon]
    keys = {c["start"] + "|" + "|".join(sorted(c["paths"])): c for c in soon}
    seen = _load("notified_conflicts") or set()
    new = [c for k, c in keys.items() if k not in seen]
    set_sync_meta("notified_conflicts", json.dumps(sorted(keys)))
    for c in new[:2]:
        send("Recording conflict",
              f"{_when(c['start'])}: {c['count']} recordings but only {c['tuners']} tuners "
              f"({', '.join(c['titles'][:4])}). Open TabloView > Scheduled > Upcoming to skip one.")
    return new


def space_level(info: Optional[Dict[str, Any]]) -> int:
    """90 or 95 when the Tablo's drive is that full (percent used), else 0."""
    if not info or not info.get("connected") or not info.get("total_gb"):
        return 0
    pct = info.get("percent_used") or 0
    return max([lvl for lvl in SPACE_LEVELS if pct >= lvl], default=0)


def deletable_shows(limit: int = 3) -> List[Dict[str, Any]]:
    """The shows with the most space in watched (not protected) recordings, biggest first."""
    shows = [s for s in get_storage_by_show() if s["watched_bytes"] > 0]
    shows.sort(key=lambda s: s["watched_bytes"], reverse=True)
    return [{"show_id": s["show_id"], "title": s["title"], "count": s["watched_count"], "bytes": s["watched_bytes"]}
            for s in shows[:limit]]


def _gb(n: float) -> str:
    return f"{n / 1024:.1f} TB" if n >= 1000 else f"{round(n)} GB"


def check_space(info: Optional[Dict[str, Any]]) -> int:
    """Announce the Tablo's drive getting almost full, once per level. Returns the level announced, or 0."""
    if not info or not info.get("connected") or not info.get("total_gb"):
        return 0
    level = space_level(info)
    try:
        seen = int(get_sync_meta("notified_space") or 0)
    except ValueError:
        seen = 0
    if level <= seen:
        if seen and (info.get("percent_used") or 0) < SPACE_REARM:
            set_sync_meta("notified_space", "0")
        return 0
    set_sync_meta("notified_space", str(level))
    tips = deletable_shows(2)
    tip = (" Watched recordings you could delete: "
           + ", ".join(f"{t['title']} (about {_gb(t['bytes'] / 1024**3)})" for t in tips) + ".") if tips else ""
    send("Your Tablo's drive is almost full",
         f"{round(info['percent_used'])}% used, {_gb(info.get('free_gb') or 0)} free.{tip} "
         "Open TabloView > Settings > Storage & exports to see what's using it.")
    return level


async def check_all(recordings: bool = True, conflicts: bool = True) -> None:
    """Run after syncs. Never raises."""
    try:
        if recordings:
            check_recordings()
            from .tablo_client import tablo_manager
            check_space(await tablo_manager.get_storage_info())
        if conflicts:
            from .routes.live import model_tuner_count
            check_conflicts(await model_tuner_count())
            from . import alerts
            alerts.notify_new()  # guide alerts: new matches since the last guide sync
    except Exception as e:
        print(f"[Notify] Check failed: {e}")
