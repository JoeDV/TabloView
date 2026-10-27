"""Automatic MP4 export of chosen shows: a backup of each new recording, made once it has finished
recording (a forum request, 2026-10-27).

Turned on per show (settings "auto_export_shows"), from the show's page. Recordings already there when
it's turned on are exported too only if asked; otherwise they're marked skipped. Each recording is
exported once (table auto_exports): deleting the MP4 doesn't bring it back, and cancelling one under
Downloads isn't undone. A failed export (the Tablo didn't answer, TabloView closed partway) is tried
again, up to TRIES times.

Exports are queued one at a time, as each finishes, so the Downloads list doesn't fill with dozens
waiting and an export started by hand isn't stuck behind them. Nothing is queued while the export
folder's drive has less than MIN_FREE_GB free. It all happens while TabloView is running: recordings
made while the PC was off are exported when it next starts (after the library sync sees them).
"""

import asyncio
import shutil
from typing import Dict, List

from .database import get_auto_exports, get_episodes_by_show, get_export_job, save_auto_export
from .settings import exports_dir, load_settings, save_settings

TRIES = 3
WORKER_INTERVAL = 60
MIN_FREE_GB = 10

status: Dict[str, object] = {"low_space": False}


def enabled_shows() -> List[str]:
    return list(load_settings().get("auto_export_shows") or [])


def waiting(show_id: str) -> int:
    """Finished recordings of this show still to be exported."""
    known = get_auto_exports([show_id])
    return sum(1 for ep in get_episodes_by_show(show_id) if ep.get("recording_state") == "finished"
               and (ep["id"] not in known or known[ep["id"]]["state"] in ("pending", "queued")))


def already_recorded(show_id: str) -> int:
    """Finished recordings of this show that turning it on would skip unless asked (not exported yet)."""
    known = get_auto_exports([show_id])
    return sum(1 for ep in get_episodes_by_show(show_id) if ep.get("recording_state") == "finished"
               and (ep["id"] not in known or known[ep["id"]]["state"] in ("skipped", "pending")))


def set_show(show_id: str, on: bool, existing: bool = False) -> int:
    """Turn automatic export on or off for a show. Turning it on, the recordings already there are
    exported too when existing is True, else only new ones. Returns how many are waiting to export."""
    save_settings({"auto_export_shows": [s for s in enabled_shows() if s != show_id] + ([show_id] if on else [])})
    if not on:
        return 0
    known = get_auto_exports([show_id])
    for ep in get_episodes_by_show(show_id):
        if ep.get("recording_state") != "finished":
            continue  # recording now (or failed): a new one, exported once it finishes
        state = known.get(ep["id"], {}).get("state")
        if state in (None, "skipped", "pending"):
            save_auto_export(ep["id"], show_id, "pending" if existing else "skipped")
    return waiting(show_id)


async def _follow_up(records: Dict[str, Dict]) -> bool:
    """Note how queued exports went. True while one is still waiting or running."""
    busy = False
    for r in records.values():
        if r["state"] != "queued":
            continue
        job = get_export_job(r["job_id"]) if r["job_id"] else None
        result = job and job["status"]
        if result in ("pending", "downloading"):
            busy = True
        elif result == "completed":
            save_auto_export(r["episode_id"], r["show_id"], "done")
        elif result == "cancelled":
            save_auto_export(r["episode_id"], r["show_id"], "cancelled")
        elif r["tries"] >= TRIES:
            save_auto_export(r["episode_id"], r["show_id"], "gave_up")
            print(f"[AutoExport] Gave up on {r['episode_id']} after {r['tries']} tries"
                  f"{': ' + job['error'] if job and job.get('error') else ''}")
        else:
            save_auto_export(r["episode_id"], r["show_id"], "pending")  # failed: again shortly
    return busy


def _low_space() -> bool:
    try:
        low = shutil.disk_usage(exports_dir()).free < MIN_FREE_GB * 1024 ** 3
    except OSError:
        low = False
    if low != status["low_space"]:
        print(f"[AutoExport] {'Less than ' + str(MIN_FREE_GB) + ' GB free where exports go: waiting' if low else 'Space again: carrying on'}")
    status["low_space"] = low
    return low


async def run_once() -> None:
    """Queue the next recording to export, if one is waiting and none is queued already."""
    from .tablo_client import tablo_manager
    from .transcode import transcode_manager
    if await _follow_up(get_auto_exports()):
        return
    shows = enabled_shows()
    if not shows or _low_space():
        return
    known = get_auto_exports(shows)
    for show_id in shows:
        for ep in get_episodes_by_show(show_id):
            r = known.get(ep["id"])
            if ep.get("recording_state") != "finished" or (r and r["state"] != "pending"):
                continue
            job = await transcode_manager.start_mp4_export(ep, tablo_manager.playlist_getter(ep["path"]))
            save_auto_export(ep["id"], show_id, "queued", job, tries=(r["tries"] if r else 0) + 1)
            print(f"[AutoExport] Exporting {ep.get('show_title')} {ep['id']}")
            return


async def worker_loop() -> None:
    from .tablo_client import tablo_manager
    while True:
        await asyncio.sleep(WORKER_INTERVAL)
        try:
            if tablo_manager.is_authenticated:
                await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[AutoExport] {e}")
