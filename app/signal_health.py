"""Signal health: which channels' recordings fail, why, and when.

The Tablo records why a recording failed (video_details.error: weak_signal, unableToTune,
tunerOffline...). Each recording's outcome is kept in recording_history after every library sync, so
the history outlasts the recordings themselves. The report groups it per channel; a channel that keeps
failing gets a notification (at most every NOTIFY_EVERY_DAYS).
"""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import get_connection, get_sync_meta, set_sync_meta, recording_details

REPORT_DAYS = 60
NOTIFY_EVERY_DAYS = 14
# "Frequent problems": at least this many in the report window, and this share of the channel's recordings
FREQUENT_COUNT = 3
FREQUENT_SHARE = 0.25

REASONS = {
    "weak_signal": "weak signal",
    "unableToTune": "couldn't tune the channel",
    "tunerOffline": "signal lost during the recording",
}


def _reason(error: Optional[Dict[str, Any]]) -> Optional[str]:
    if not error:
        return None
    desc = str(error.get("description") or "")
    for key in ("unableToTune", "tunerOffline"):
        if key in desc:
            return key
    return error.get("details") or error.get("code") or "failed"


def update_history() -> int:
    """Remember the outcome of every finished or failed recording in the library. Returns how many."""
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    with get_connection() as conn:
        for r in conn.execute("SELECT id, show_title, air_date, duration, raw_json FROM episodes"):
            try:
                raw = json.loads(r["raw_json"] or "{}")
            except ValueError:
                continue
            d = recording_details(raw)
            if d["recording_state"] not in ("finished", "failed"):
                continue  # still recording, or not started
            ch = ((raw.get("airing_details") or {}).get("channel") or {}).get("channel") or {}
            number = f"{ch.get('major')}.{ch.get('minor')}" if ch.get("major") else ""
            error = (raw.get("video_details") or {}).get("error")
            rows.append((r["id"], r["show_title"], r["air_date"], number, ch.get("call_sign") or "", ch.get("network") or "",
                         d["recording_state"], 1 if d["incomplete"] else 0, _reason(error) if d["incomplete"] else None, now))
        conn.executemany("""
            INSERT INTO recording_history (episode_id, show_title, air_date, channel, call_sign, network, state, problem, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_id) DO UPDATE SET state = excluded.state, problem = excluded.problem,
                reason = excluded.reason, updated_at = excluded.updated_at
        """, rows)
        conn.commit()
    return len(rows)


def _when(hours: List[int]) -> Optional[str]:
    """'mostly 7–8 PM' when most problems fall in the same hour of the day."""
    if len(hours) < 2:
        return None
    hour, n = Counter(hours).most_common(1)[0]
    if n / len(hours) < 0.6:
        return None
    fmt = lambda h: f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
    return f"mostly {fmt(hour).split()[0]}–{fmt((hour + 1) % 24)}"


def report(days: int = REPORT_DAYS, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Per channel over the last `days`: recordings, problems, the main reason, when they happen, a verdict."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM recording_history WHERE air_date >= ? AND channel != ''", (since,))]
    channels: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        c = channels.setdefault(r["channel"], {"channel": r["channel"], "call_sign": r["call_sign"], "network": r["network"],
                                               "recordings": 0, "problems": 0, "reasons": Counter(), "hours": [], "last_problem": None})
        c["recordings"] += 1
        if r["problem"]:
            c["problems"] += 1
            c["reasons"][r["reason"] or "failed"] += 1
            try:
                c["hours"].append(datetime.fromisoformat(r["air_date"].replace("Z", "+00:00")).astimezone().hour)
            except ValueError:
                pass
            c["last_problem"] = max(c["last_problem"] or "", r["air_date"])
    result = []
    for c in channels.values():
        share = c["problems"] / c["recordings"]
        main = c["reasons"].most_common(1)[0][0] if c["reasons"] else None
        result.append({
            "channel": c["channel"], "call_sign": c["call_sign"], "network": c["network"],
            "recordings": c["recordings"], "problems": c["problems"],
            "reason": REASONS.get(main, main) if main else None, "signal": main in ("weak_signal", "unableToTune", "tunerOffline"),
            "when": _when(c["hours"]), "last_problem": c["last_problem"],
            "status": "frequent" if c["problems"] >= FREQUENT_COUNT and share >= FREQUENT_SHARE
                      else "some" if c["problems"] else "ok",
        })
    order = {"frequent": 0, "some": 1, "ok": 2}
    return sorted(result, key=lambda c: (order[c["status"]], -c["problems"], c["channel"]))


def check() -> List[Dict[str, Any]]:
    """After a library sync: update the history and notify about channels with frequent problems
    (each at most every NOTIFY_EVERY_DAYS). Never raises."""
    from .notifications import send
    try:
        update_history()
        now = datetime.now(timezone.utc)
        notified = json.loads(get_sync_meta("signal_notified") or "{}")
        flagged = []
        for c in report(now=now):
            if c["status"] != "frequent":
                continue
            last = notified.get(c["channel"])
            if last and now - datetime.fromisoformat(last) < timedelta(days=NOTIFY_EVERY_DAYS):
                continue
            notified[c["channel"]] = now.isoformat()
            flagged.append(c)
            reason = f" ({c['reason']})" if c["reason"] else ""
            when = f", {c['when']}" if c["when"] else ""
            send("Recording problems on one channel",
                 f"{c['channel']} {c['call_sign']}: {c['problems']} of {c['recordings']} recordings had problems"
                 f"{reason}{when}. Device → Signal health has tips.")
        if flagged:
            set_sync_meta("signal_notified", json.dumps(notified))
        return flagged
    except Exception as e:
        print(f"[SignalHealth] {e}")
        return []
