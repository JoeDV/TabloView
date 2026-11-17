"""Moving TabloView to another PC: everything set up in it, in one file to save and open on the new PC.

In the file: the settings (Settings, each show's options: commercials, automatic export, delete after
watching, Plex's delete-once-in-Plex; Home's layout; More channels), the Watch list, live TV reminders,
commercial breaks and signal dropouts already found (finding them again takes hours, and money with
Claude), signal health's history, and which recordings were exported automatically already (else
the new PC would export them all again). The browser's own preferences (player volume, captions,
buffer...) come from the page that asks, and go back to the page that restores.

Left out, so the file is safe to keep anywhere: the Tablo sign-in, the Plex sign-in, the Claude API
key and the network PIN. They're set up again on the new PC. Also left out: things about the PC itself
(its port, start with Windows, network access)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import reminders
from .config import APP_VERSION
from .database import get_connection
from .settings import DEFAULTS, load_settings, save_settings

FORMAT = 1
KIND = "TabloView backup"

# Settings that aren't moved: sign-ins and secrets, things about this PC, and TabloView's own notes
# of what it has done here
NOT_MOVED = {
    "lan_pin", "lan_secret", "lan_generation", "allow_lan", "port", "closing_notice_shown",
    "plex_client_id", "plex_token", "plex_server",
    "claude_api_key", "claude_key_added", "claude_error", "claude_last_cost",
    "last_seen_version", "long_logo_breaks_redone", "commercial_redo",
}
# Tables copied as they are: (table, key column)
TABLES = [("commercials", "episode_id"), ("dropouts", "episode_id"), ("recording_history", "episode_id"),
          ("auto_exports", "episode_id")]
# The browser's preferences that move (localStorage keys in static/app.js); not which view this
# browser opens in
BROWSER_KEYS = ["tablo_buffer_target", "tablo_autoplay", "tablo_cc", "tablo_cc_second", "tablo_volume",
                "tv_start_page", "tv_lib_sort", "tv_lib_layout"]


class BackupError(ValueError):
    """The file can't be restored; the message says why, for the person restoring it."""


def _rows(table: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]


def make(browser: Dict[str, Any]) -> Dict[str, Any]:
    """The backup, as a dict to save as JSON."""
    settings = {k: v for k, v in load_settings().items() if k in DEFAULTS and k not in NOT_MOVED}
    with get_connection() as conn:
        watch = [r[0] for r in conn.execute("SELECT episode_id FROM watch_list ORDER BY sort_order").fetchall()]
    return {
        "kind": KIND, "format": FORMAT, "version": APP_VERSION,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": settings,
        "watch_list": watch,
        "reminders": reminders.listing(),
        "tables": {t: _rows(t) for t, _ in TABLES},
        "browser": {k: str(v) for k, v in (browser or {}).items() if k in BROWSER_KEYS and v is not None},
    }


def summary(data: Dict[str, Any]) -> Dict[str, int]:
    tables = data.get("tables") or {}
    return {
        "settings": len(data.get("settings") or {}),
        "watch_list": len(data.get("watch_list") or []),
        "reminders": len(data.get("reminders") or []),
        "commercials": len(tables.get("commercials") or []),
        "dropouts": len(tables.get("dropouts") or []),
        "history": len(tables.get("recording_history") or []),
        "auto_exports": len(tables.get("auto_exports") or []),
    }


def _check(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise BackupError("This isn't a TabloView backup file.")
    if int(data.get("format") or 0) > FORMAT:
        raise BackupError(f"This backup is from a newer TabloView ({data.get('version')}). Update TabloView on this PC first.")
    return data


def restore(data: Any) -> Dict[str, Any]:
    """Bring a backup in. Settings in it replace this PC's (the ones left out stay as they are);
    the Watch list, reminders and the rest are added to what's here, keeping what's here where both
    have the same recording. Returns what was restored, and the browser preferences for the page."""
    data = _check(data)
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM episodes LIMIT 1").fetchone():
            # The Watch list keeps only recordings it knows; restoring before the first sync would lose it
            raise BackupError("Sign in to your Tablo and let TabloView finish reading your recordings first, then restore.")
    notes: List[str] = []

    # Settings
    incoming = {k: v for k, v in (data.get("settings") or {}).items() if k in DEFAULTS and k not in NOT_MOVED}
    folder = incoming.get("export_folder")
    if folder and not Path(folder).is_dir():
        incoming.pop("export_folder")
        notes.append(f"The export folder ({folder}) isn't on this PC, so exports still go to {load_settings().get('export_folder') or 'Downloads'}. Change it in Settings → Storage & exports.")
    save_settings(incoming)

    # Tables: rows for recordings this PC doesn't have yet; columns this version knows
    added: Dict[str, int] = {}
    with get_connection() as conn:
        for table, key in TABLES:
            rows = (data.get("tables") or {}).get(table) or []
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            count = 0
            for row in rows:
                if not isinstance(row, dict) or not row.get(key):
                    continue
                row = {c: row.get(c) for c in cols if c in row}
                if table == "auto_exports" and row.get("state") == "queued":
                    row.update(state="pending", job_id=None)  # its export was on the other PC
                names = ", ".join(row)
                cur = conn.execute(f"INSERT OR IGNORE INTO {table} ({names}) VALUES ({', '.join('?' * len(row))})",
                                   list(row.values()))
                count += cur.rowcount
            added[table] = count
        # Watch list: the backup's recordings after any already listed here, ones on this Tablo only
        known = {r[0] for r in conn.execute("SELECT id FROM episodes").fetchall()}
        listed = {r[0] for r in conn.execute("SELECT episode_id FROM watch_list").fetchall()}
        last = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM watch_list").fetchone()[0]
        wanted = [i for i in dict.fromkeys(data.get("watch_list") or []) if isinstance(i, str)]
        new = [i for i in wanted if i in known and i not in listed]
        conn.executemany("INSERT INTO watch_list (episode_id, sort_order) VALUES (?, ?)",
                         [(i, last + n + 1) for n, i in enumerate(new)])
        conn.commit()
    gone = sum(1 for i in wanted if i not in known)
    if gone:
        notes.append(f"{gone} recording{'s' if gone != 1 else ''} on the Watch list {'aren’t' if gone != 1 else 'isn’t'} on this Tablo any more.")

    # Reminders still to come
    have = {reminders.reminder_id(r["channel_key"], r["start"]) for r in reminders.listing()}
    added_reminders = 0
    now = datetime.now(timezone.utc)
    for r in data.get("reminders") or []:
        try:
            if reminders.reminder_id(r["channel_key"], r["start"]) not in have and reminders._current([r], now):
                reminders.add(r)
                added_reminders += 1
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "from_version": data.get("version"), "created": data.get("created"),
        "settings": len(incoming), "watch_list": len(new), "reminders": added_reminders,
        "commercials": added.get("commercials", 0), "dropouts": added.get("dropouts", 0),
        "history": added.get("recording_history", 0), "auto_exports": added.get("auto_exports", 0),
        "browser": {k: str(v) for k, v in (data.get("browser") or {}).items() if k in BROWSER_KEYS},
        "notes": notes,
    }


def dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False)
