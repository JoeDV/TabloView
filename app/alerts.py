"""Guide alerts: words to watch for in the antenna guide, such as a team, a movie or a special
("Eagles", "Wizard of Oz", "Jeopardy! Masters"). Series rules can't catch one-off airings like
these. Matches show on Home with a Record button, and a notification says when new ones appear
(after a guide sync).

Matched against each airing's show and episode titles (a game's teams are its episode title), as
whole words, ignoring case. Built from the guide TabloView already keeps: nothing extra is asked of
the Tablo."""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import get_connection, get_sync_meta, set_sync_meta
from .settings import load_settings, save_settings

MAX_WORDS = 30
MAX_MATCHES = 60
MAX_PER_WORD = 15  # a broad word ("Football") doesn't crowd out the others' matches


class AlertError(ValueError):
    pass


def words() -> List[str]:
    return [w for w in load_settings().get("guide_alerts") or [] if isinstance(w, str) and w.strip()]


def add(word: str) -> List[str]:
    word = " ".join((word or "").split())
    if len(word) < 2:
        raise AlertError("Type at least two letters.")
    if len(word) > 60:
        raise AlertError("That's too long for a guide alert (60 letters at most).")
    current = words()
    if any(w.lower() == word.lower() for w in current):
        return current
    if len(current) >= MAX_WORDS:
        raise AlertError(f"You have {MAX_WORDS} guide alerts already: remove one first.")
    current.append(word)
    save_settings({"guide_alerts": current})
    return current


def remove(word: str) -> List[str]:
    current = [w for w in words() if w.lower() != (word or "").strip().lower()]
    save_settings({"guide_alerts": current})
    return current


def _pattern(word: str) -> "re.Pattern[str]":
    # Whole words: "Eagles" isn't in "Seagles"; edges that aren't letters ("Jeopardy!") still work
    return re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE)


def matches(alert_words: Optional[List[str]] = None, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Airings in the guide that haven't ended, whose titles have one of the words, soonest first,
    each with the word it matched ('alert') and the show's art."""
    alert_words = words() if alert_words is None else alert_words
    if not alert_words:
        return []
    patterns = [(w, _pattern(w)) for w in alert_words]
    now = now or datetime.now(timezone.utc)
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT ga.path, ga.series_path, ga.show_title, ga.episode_title, ga.season_number, ga.episode_number,
                   ga.air_datetime, ga.duration, ga.channel_call_sign, ga.channel_network, ga.is_new,
                   ga.is_premiere, ga.schedule_state, ga.channel_identifier, g.cover_url, g.backdrop_url
            FROM guide_airings ga
            LEFT JOIN guide_shows g ON g.path = ga.series_path
            ORDER BY ga.air_datetime ASC, ga.show_title
        """).fetchall()]
    found: List[Dict[str, Any]] = []
    per_word: Dict[str, int] = {}
    for r in rows:
        try:
            start = datetime.fromisoformat(str(r["air_datetime"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if start + timedelta(seconds=int(r["duration"] or 0)) <= now:
            continue
        text = f"{r['show_title'] or ''} {r['episode_title'] or ''}"
        hit = next((w for w, p in patterns if p.search(text) and per_word.get(w, 0) < MAX_PER_WORD), None)
        if hit:
            per_word[hit] = per_word.get(hit, 0) + 1
            r["alert"] = hit
            r["is_new"] = bool(r["is_new"])
            r["is_premiere"] = bool(r["is_premiere"])
            r["scheduled"] = r["schedule_state"] in ("scheduled", "conflicted")
            found.append(r)
            if len(found) >= MAX_MATCHES:
                break
    return found


def notify_new() -> List[Dict[str, Any]]:
    """After a guide sync: one notification for matches not announced before. The first time, the
    matches there already are taken as known, so turning this on doesn't bring a flood."""
    from . import notifications
    found = matches()
    keys = {m["path"]: m for m in found}
    raw = get_sync_meta("notified_alerts")
    try:
        seen = set(json.loads(raw)) if raw else None
    except ValueError:
        seen = None
    set_sync_meta("notified_alerts", json.dumps(sorted(keys)))
    if seen is None:
        return []
    new = [m for p, m in keys.items() if p not in seen and not m["scheduled"]]
    if new:
        names = ", ".join(dict.fromkeys(m["show_title"] + (f": {m['episode_title']}" if m["episode_title"] else "")
                                        for m in new[:3]))
        more = f" and {len(new) - 3} more" if len(new) > 3 else ""
        notifications.send("Guide alert", f"{names}{more}. Open TabloView's Home to record.")
    return new
