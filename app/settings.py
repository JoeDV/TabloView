"""Small persisted app settings (data/settings.json), separate from Tablo credentials."""

import json
from typing import Any, Dict

from .config import SETTINGS_FILE

DEFAULTS: Dict[str, Any] = {
    "allow_lan": False,  # packaged app: listen on all interfaces instead of 127.0.0.1 only
    "port": 7070,
    "auto_sync_minutes": 15,  # recordings sync interval; 0 = off (guide refreshes every GUIDE_SYNC_HOURS)
    "notifications": True,  # tray notifications for failed/short recordings and recording conflicts
    "video_quality": "auto",  # browser playback: auto (graphics chip if available), best, fastest
    "smooth_motion": None,  # 60 fps from 1080i; None = on when a graphics-chip encoder is in use
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


def save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    data = load_settings()
    data.update({k: v for k, v in updates.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
