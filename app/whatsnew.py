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
    "1.1.6": [
        "Much faster loading from your Tablo: a new computer's first load takes under a minute instead of 5–10, and \"Tablo isn't responding\" during loading is gone.",
        "A banner shows progress while the TV guide loads for the first time.",
        "Preview frames when you hover over a recording's timeline.",
        "Sleep timer in the player: stop after 15–90 minutes or at the end of the show.",
        "On now: what's airing on your channels, right on the Home page.",
        "Smaller MP4 exports (about a third smaller), and export several episodes at once.",
        "Playback recovers when the video converter crashes, instead of stopping as if the show had ended.",
    ],
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
        "Far fewer \"Tablo isn't responding\" interruptions: refreshing the guide no longer floods the Tablo with requests. When it does happen, TabloView says so and reconnects on its own.",
    ],
    "1.1.4": [
        "Episode thumbnails taken from the recordings themselves.",
        "Auto-play the next episode when one ends.",
        "Device → Space by show: see which shows use the most space and delete their watched episodes in one click.",
        "Start with Windows (in the tray), and Windows notifications for failed recordings and recording conflicts.",
        "Protected recordings show a lock, and Delete watched skips them.",
        "Clearer tags for recordings that came out short, failed, or had signal problems.",
        "A Favorites filter in Live TV (favorites set in the Tablo app).",
        "Playback starts where the show does, skipping the few seconds the Tablo records early.",
    ],
    "1.1.3": [
        "Available in the Microsoft Store.",
        "No more console windows popping up during playback.",
    ],
    "1.1.2": [
        "Scheduled → Upcoming: every recording coming up, with warnings when more are set to record at once than you have tuners.",
        "Live TV warns before tuning would leave too few tuners for a recording about to start, and shows tuners the Tablo is still releasing.",
        "A timeline in the player to jump around a recording.",
    ],
    "1.1.1": [
        "TabloView tells you when a new version is available.",
        "Live TV: talk shows no longer count as News.",
    ],
    "1.1.0": [
        "Watched status and resume points, shared with the Tablo's own apps.",
        "Live TV works in any TV market.",
        "A banner when your Tablo sign-in has expired, with a button to sign in again.",
        "Recordings sync automatically every 15 minutes (adjustable), and the guide every 6 hours.",
        "Scheduled lists every series set to record, including ones between seasons.",
    ],
    "1.0.0": [
        "First release: recordings, the program guide, live TV, series scheduling and MP4 export for the Tablo 4th Gen, in a Windows app with its own installer.",
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


def changelog() -> List[Dict[str, Any]]:
    """Every version's notes, newest first, up to the one running (for Device → Version history)."""
    def key(v: str):
        return tuple(int(x) for x in v.split("."))
    return [{"version": v, "notes": n} for v, n in NOTES.items() if key(v) <= key(APP_VERSION)]


def mark_seen() -> None:
    save_settings({"last_seen_version": APP_VERSION})
