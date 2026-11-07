"""Remind me: for shows on More channels (app/extra_channels.py), which can't be recorded. At the show's
start the desktop app shows a Windows notification, and open TabloView pages (the PC's and the TV
view) show it with a Watch button: they ask for due() every half minute.

Kept in REMINDERS_FILE; a reminder is dropped once its show has ended.
"""
import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import DATA_DIR
from . import notifications

REMINDERS_FILE = DATA_DIR / "reminders.json"
CHECK_SECONDS = 30
SHOWN_FOR_SECONDS = 300  # pages show a reminder for the first 5 minutes of the show
MAX_REMINDERS = 200

_lock = threading.Lock()


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _load() -> List[Dict[str, Any]]:
    try:
        data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = REMINDERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1), encoding="utf-8")
    tmp.replace(REMINDERS_FILE)


def _current(items: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Those whose show hasn't ended."""
    return [r for r in items if _parse(r["start"]) + timedelta(seconds=int(r.get("duration") or 0)) > now]


def listing(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    with _lock:
        return sorted(_current(_load(), now), key=lambda r: r["start"])


def reminder_id(channel_key: str, start: str) -> str:
    return f"{channel_key}@{start}"


def add(r: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """{channel_key, channel_id, channel_name, title, episode_title, start (ISO), duration (s)}."""
    now = now or datetime.now(timezone.utc)
    item = {k: r.get(k) for k in ("channel_key", "channel_id", "channel_name", "title", "episode_title", "start", "duration")}
    item["id"] = reminder_id(item["channel_key"], item["start"])
    item["notified"] = False
    with _lock:
        items = [x for x in _current(_load(), now) if x["id"] != item["id"]]
        if len(items) >= MAX_REMINDERS:
            raise ValueError(f"You have {MAX_REMINDERS} reminders already.")
        items.append(item)
        _save(items)
    return item


def remove(rid: str) -> None:
    with _lock:
        items = _load()
        _save([x for x in items if x["id"] != rid])


def due(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Shows that started in the last SHOWN_FOR_SECONDS (for the pages)."""
    now = now or datetime.now(timezone.utc)
    return [r for r in listing(now) if timedelta(0) <= now - _parse(r["start"]) < timedelta(seconds=SHOWN_FOR_SECONDS)]


def notify_due(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The Windows notification for each reminder that's due, once."""
    now = now or datetime.now(timezone.utc)
    sent = []
    with _lock:
        items = _current(_load(), now)
        for r in items:
            if not r.get("notified") and _parse(r["start"]) <= now:
                r["notified"] = True
                sent.append(r)
        if sent or len(items) != len(_load()):
            _save(items)
    for r in sent:
        notifications.send(f"Starting now on {r['channel_name']}",
                           f"{r['title']}{': ' + r['episode_title'] if r.get('episode_title') else ''}. Open TabloView to watch.")
    return sent


async def worker_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(notify_due)
        except Exception as e:
            print(f"[Reminders] {e!r}")
        await asyncio.sleep(CHECK_SECONDS)
