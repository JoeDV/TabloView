"""Upcoming recordings as an iCalendar (.ics) file, to import into Google Calendar, Outlook or Apple Calendar.

Each event's UID is fixed per airing, so importing a newer file into the same calendar updates the
events rather than adding copies. Times are UTC; the calendar shows them in local time.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets continue on the next line after a space."""
    out, data = [], line.encode("utf-8")
    while len(data) > 75:
        cut = 75
        while cut > 0 and (data[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data = b" " + data[cut:]
    out.append(data.decode("utf-8"))
    return "\r\n".join(out)


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build(recordings: List[Dict[str, Any]], now: datetime = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TabloView//Upcoming recordings//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:TabloView recordings"]
    for a in recordings:
        try:
            start = datetime.fromisoformat(a["air_datetime"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        end = start + timedelta(seconds=int(a.get("duration") or 1800))
        s, e = a.get("season_number") or 0, a.get("episode_number") or 0
        se = f"S{s}E{e}" if s and e else ""
        episode = " · ".join(x for x in (se, a.get("episode_title") or "") if x)
        channel = " ".join(x for x in (a.get("channel_network") or "", a.get("channel_call_sign") or "") if x)
        # The show name alone as the title (calendar views cut long titles); the episode goes in the details
        details = ([episode] if episode else []) + [f"Recording on your Tablo{f' from {channel}' if channel else ''}."]
        if a.get("is_new"):
            details.append("New episode.")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{a['path'].strip('/').replace('/', '-')}@tabloview",
            f"DTSTAMP:{_stamp(now)}",
            f"DTSTART:{_stamp(start)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{_escape(a.get('show_title') or 'Recording')}",
            f"DESCRIPTION:{_escape(chr(10).join(details))}",
            *([f"LOCATION:{_escape(channel)}"] if channel else []),
            "TRANSP:TRANSPARENT",  # doesn't make you look busy
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
