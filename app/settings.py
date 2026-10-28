"""Small persisted app settings (data/settings.json), separate from Tablo credentials.

Saved safely: written to a temporary file that then replaces settings.json in one step, so TabloView
ending mid-save can't leave half a file, and the previous good copy is kept as settings.bak.json.
A settings.json that can't be read anyway is read from that copy, rather than starting from the
defaults and saving them over everything (the PIN, the export folder, the commercial-finder shows).
"""

import json
import os
import shutil
import threading
import time
from typing import Any, Dict, Optional

from pathlib import Path

from .config import SETTINGS_FILE, DOWNLOADS_DIR

BACKUP_FILE = SETTINGS_FILE.with_name("settings.bak.json")
_save_lock = threading.Lock()  # one save at a time (some run in worker threads)
_damaged_said: list = []

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
    "export_show_folders": False,  # exports go in Show\Season 01\ folders (the layout Plex, Jellyfin and Kodi expect)
    "export_nfo": False,  # a Kodi-style .nfo file beside each export (Jellyfin, Emby, Kodi read them)
    "rerecord_failed": True,  # schedule a rerun of a recording that failed or came out short (app/rerecord.py)
    "commercial_shows": [],  # show ids whose recordings get commercial breaks found (app/commercials.py)
    "commercial_episodes": [],  # single recordings asked for from the episode menu
    "auto_export_shows": [],  # show ids whose new recordings are exported to MP4 automatically (app/autoexport.py)
    "skip_commercials": False,  # skip breaks automatically in the player (otherwise a Skip button)
    "skip_dropouts": False,  # skip signal dropouts in recordings automatically (otherwise a Skip button)
    "picture_shapes": {},  # channel identifier -> "4:3", "16:9" or "zoom" in the player (no entry = as broadcast)
    "cleanup_days": {},  # show_id -> delete watched recordings this many days after watching (app/cleanup.py)
    "home_order": [],  # Home's sections in the order chosen (ids from static/app.js HOME_SECTIONS); [] = as designed
    "home_hidden": [],  # Home sections turned off (also in TV view)
    "last_seen_version": None,  # newest version whose "What's new" card was shown (app/whatsnew.py)
}

GUIDE_SYNC_HOURS = 6


def _read(path: Path) -> Optional[Dict[str, Any]]:
    """The settings in this file, or None when it's missing or isn't valid."""
    for _ in range(5):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except PermissionError:  # Windows: being replaced this instant
            time.sleep(0.05)
        except (OSError, ValueError) as e:
            print(f"[Settings] Couldn't read {path.name}: {e}")
            return None
    return None


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    saved = _read(SETTINGS_FILE)
    if saved is None and SETTINGS_FILE.exists():
        saved = _read(BACKUP_FILE)
        if not _damaged_said:  # once, not on every request
            _damaged_said.append(True)
            print(f"[Settings] settings.json is damaged; {'using the copy from the save before' if saved is not None else 'no good copy, using defaults'}")
    data.update(saved or {})
    return data


def _replace(src: Path, dst: Path) -> None:
    # Windows refuses for a moment while something reads the file being replaced
    for attempt in range(10):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


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
    with _save_lock:
        data = load_settings()
        data.update({k: v for k, v in updates.items() if k in DEFAULTS})
        tmp = SETTINGS_FILE.with_name("settings.json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if _read(SETTINGS_FILE) is not None:  # keep the last good copy, never a damaged one
            try:
                shutil.copyfile(SETTINGS_FILE, BACKUP_FILE)
            except OSError as e:
                print(f"[Settings] Couldn't keep a backup copy: {e}")
        _replace(tmp, SETTINGS_FILE)
    return data
