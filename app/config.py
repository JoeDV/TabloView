"""Configuration and environment management for TabloView.

Two layouts:
- Source checkout (developer): everything lives next to the code, as before.
- Packaged app (PyInstaller): bundled files are read-only in the install folder; each Windows
  user's settings, cache and transcodes live in %LOCALAPPDATA%\\TabloView, and MP4 exports go
  to their Downloads\\TabloView folder.
"""

import os
import sys
import shutil
from pathlib import Path

APP_NAME = "TabloView"
APP_VERSION = "1.1.0"

# Update notices: a public URL to version.json ({"version", "download_url", "notes"}), written by
# packaging/build.ps1 next to the installer. Empty = don't check. TABLOVIEW_UPDATE_URL overrides.
UPDATE_INFO_URL = ""
# Where people download the installer; build.ps1 copies this into version.json
RELEASE_DOWNLOAD_URL = ""

IS_PACKAGED = getattr(sys, "frozen", False)

# Read-only resources (static UI, bundled ffmpeg)
BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
STATIC_DIR = RESOURCE_DIR / "static"

if IS_PACKAGED:
    _local = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    HOME_DIR = Path(os.getenv("TABLOVIEW_HOME") or _local / APP_NAME)
    DOWNLOADS_DIR = Path.home() / "Downloads" / APP_NAME
else:
    # Developer checkout: credentials may come from .env next to the code
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    HOME_DIR = Path(os.getenv("TABLOVIEW_HOME") or BASE_DIR)
    DOWNLOADS_DIR = HOME_DIR / "downloads"

DATA_DIR = HOME_DIR / "data"
TRANSCODE_DIR = HOME_DIR / "transcode"
LOG_DIR = HOME_DIR / "logs"
IMAGE_CACHE_DIR = DATA_DIR / "images"

for _d in (DATA_DIR, TRANSCODE_DIR, DOWNLOADS_DIR, IMAGE_CACHE_DIR, LOG_DIR):
    _d.mkdir(exist_ok=True, parents=True)

CONFIG_FILE = DATA_DIR / "config.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "tablo_cache.db"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "7070"))

# Only honoured in a developer checkout; packaged users sign in through the UI
TABLO_EMAIL = "" if IS_PACKAGED else os.getenv("TABLO_EMAIL", "")
TABLO_PASSWORD = "" if IS_PACKAGED else os.getenv("TABLO_PASSWORD", "")


def find_ffmpeg() -> str:
    """Locate ffmpeg: bundled copy first, then PATH, then the WinGet install location."""
    bundled = RESOURCE_DIR / "ffmpeg" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)

    found = shutil.which("ffmpeg")
    if found:
        return found

    user_profile = os.getenv("USERPROFILE", "")
    if user_profile:
        winget_path = Path(user_profile) / "AppData/Local/Microsoft/WinGet/Packages"
        if winget_path.exists():
            for p in winget_path.glob("**/ffmpeg.exe"):
                if p.is_file():
                    return str(p)

    return "ffmpeg"


FFMPEG_PATH = find_ffmpeg()
