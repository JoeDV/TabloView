"""Small persisted app settings (data/settings.json), separate from Tablo credentials."""

import json
from typing import Any, Dict

from pathlib import Path

from .config import SETTINGS_FILE, DOWNLOADS_DIR

DEFAULTS: Dict[str, Any] = {
    "closing_notice_shown": False,  # the tray has said once that closing the browser doesn't quit
    "allow_lan": False,  # packaged app: listen on all interfaces instead of 127.0.0.1 only
    "lan_pin": None,  # {salt, hash}: PIN other devices sign in with (app/lanauth.py)
    "lan_secret": None,  # signs the "remembered device" cookies
    "lan_generation": 0,  # bumped to sign out every remembered device
    "port": 7070,
    "auto_sync_minutes": 15,  # recordings sync interval; 0 = off (guide refreshes every GUIDE_SYNC_HOURS)
    "notifications": True,  # tray notifications for failed/short recordings and recording conflicts
    "video_quality": "auto",  # browser playback: auto (graphics chip if available), best, fastest
    "smooth_motion": False,  # 60 fps from 1080i (opt-in: harder on graphics-chip encoders)
    "logo_style": "color",  # channel logos: "color" (the station's own) or "white"
    "export_format": "smaller",  # MP4 exports: "smaller" (H.264, graphics chip if available) or "original" (exact copy)
    "export_folder": None,  # where MP4 exports go; None = DOWNLOADS_DIR (Downloads\TabloView)
    "rerecord_failed": True,  # schedule a rerun of a recording that failed or came out short (app/rerecord.py)
    "commercial_shows": [],  # show ids whose recordings get commercial breaks found (app/commercials.py)
    "commercial_episodes": [],  # single recordings asked for from the episode menu
    "skip_commercials": False,  # skip breaks automatically in the player (otherwise a Skip button)
    "skip_dropouts": False,  # skip signal dropouts in recordings automatically (otherwise a Skip button)
    "cleanup_days": {},  # show_id -> delete watched recordings this many days after watching (app/cleanup.py)
    "last_seen_version": None,  # newest version whose "What's new" card was shown (app/whatsnew.py)
}

GUIDE_SYNC_HOURS = 6


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"[Settings] Could not read settings, using defaults: {e}")
    return data


def exports_dir() -> Path:
    """Where MP4 exports are saved: the chosen folder, or Downloads\\TabloView. Falls back to the default
    if the chosen folder can't be used any more (e.g. a removed USB drive)."""
    custom = load_settings().get("export_folder")
    if custom:
        try:
            p = Path(custom)
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError as e:
            print(f"[Settings] Export folder {custom} isn't available ({e}); using {DOWNLOADS_DIR}")
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOADS_DIR


def save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    data = load_settings()
    data.update({k: v for k, v in updates.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
