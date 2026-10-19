"""'What's new' card shown once after TabloView updates (the only way Store users hear about changes).

The last version shown is kept in settings ('last_seen_version'). A fresh install starts as seen,
so new users aren't greeted with release notes; someone who already used an older version (there
was a sync before this run started) sees the notes for the current version.
"""

from typing import Any, Dict, List

from .config import APP_VERSION
from .database import get_sync_meta
from .settings import load_settings, save_settings

# Newest first. Keep in step with packaging/release-notes.txt and the Store listing's "What's new".
NOTES: Dict[str, List[str]] = {
    "1.1.5": [
        "Sharper playback: your PC's graphics chip converts the video when it can. For sports, try Smooth motion (60 fps) in Device → Playback.",
        "Streaming channels play in their original quality and start faster.",
        "Clearer dialogue in shows with surround sound.",
        "Player controls: skip back 10 s / ahead 30 s, pause, speed, picture-in-picture and full screen, with keyboard shortcuts (press ? in the player).",
        "Pause and rewind live TV, up to 30 minutes.",
        "Change channels without leaving the player: press C for a list of what's on, or Page Up / Page Down.",
        "Protect recordings from deletion (episode menu), and on a show's page choose how many recordings your Tablo keeps, or have watched ones deleted automatically after a few days.",
        "Playback that stalls picks up again on its own.",
        "Recording conflicts can be fixed in a click: TabloView finds another airing of the same episode to record instead.",
    ],
}


def init() -> None:
    """At startup: decide whether this is an upgrade (show notes) or a fresh install (don't)."""
    if load_settings().get("last_seen_version") is None and not get_sync_meta("last_sync"):
        save_settings({"last_seen_version": APP_VERSION})


def pending() -> Dict[str, Any]:
    seen = load_settings().get("last_seen_version")
    notes = NOTES.get(APP_VERSION, [])
    return {"show": seen != APP_VERSION and bool(notes), "version": APP_VERSION, "notes": notes}


def mark_seen() -> None:
    save_settings({"last_seen_version": APP_VERSION})
