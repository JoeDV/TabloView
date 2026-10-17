"""Configuration and environment management for Tablo Classic UI."""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)

DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True, parents=True)

TRANSCODE_DIR = BASE_DIR / "transcode"
TRANSCODE_DIR.mkdir(exist_ok=True, parents=True)

IMAGE_CACHE_DIR = DATA_DIR / "images"
IMAGE_CACHE_DIR.mkdir(exist_ok=True, parents=True)

CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "tablo_cache.db"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "7070"))

TABLO_EMAIL = os.getenv("TABLO_EMAIL", "")
TABLO_PASSWORD = os.getenv("TABLO_PASSWORD", "")

def find_ffmpeg() -> str:
    """Locate ffmpeg binary on the system."""
    # 1. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    
    # 2. Windows WinGet default location for Gyan.FFmpeg
    user_profile = os.getenv("USERPROFILE", "")
    if user_profile:
        winget_path = Path(user_profile) / "AppData/Local/Microsoft/WinGet/Packages"
        if winget_path.exists():
            for p in winget_path.glob("**/ffmpeg.exe"):
                if p.is_file():
                    return str(p)

    return "ffmpeg"

FFMPEG_PATH = find_ffmpeg()
