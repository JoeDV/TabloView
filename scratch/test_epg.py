import sys
sys.path.insert(0, '.')
import sqlite3
import json
from datetime import datetime, timezone, timedelta

def get_epg_data(hours=6, start_iso=None):
    conn = sqlite3.connect('data/tablo_cache.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if start_iso:
        dt_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    else:
        now = datetime.now(timezone.utc)
        # Round down to previous 30-minute mark
        minute = 30 if now.minute >= 30 else 0
        dt_start = now.replace(minute=minute, second=0, microsecond=0)
        # Show from 30 mins before current time to catch start of current show
        dt_start = dt_start - timedelta(minutes=30)

    dt_end = dt_start + timedelta(hours=hours)

    start_str = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = dt_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"EPG Window: {start_str} to {end_str} ({hours} hours)")

    # Generate 30-min time slots
    slots = []
    curr = dt_start
    while curr < dt_end:
        slots.append({
            "iso": curr.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_str": curr.strftime("%I:%M %p").lstrip("0"),
        })
        curr += timedelta(minutes=30)

    rows = c.execute("""
        SELECT path, series_path, show_title, episode_title, season_number, episode_number,
               air_datetime, duration, channel_call_sign, channel_network, qualifiers,
               is_new, is_primetime, is_premiere
        FROM guide_airings
        WHERE datetime(air_datetime, '+' || duration || ' seconds') > datetime(?)
          AND datetime(air_datetime) < datetime(?)
        ORDER BY air_datetime ASC
    """, (start_str, end_str)).fetchall()

    print(f"Total overlapping airings: {len(rows)}")
    by_channel = {}
    for r in rows:
        cs = (r["channel_call_sign"] or "").strip()
        if cs:
            by_channel.setdefault(cs, []).append(dict(r))

    for cs, airings in by_channel.items():
        print(f"  Channel {cs}: {len(airings)} airings")

    return {
        "start_iso": start_str,
        "end_iso": end_str,
        "slots": slots,
        "by_channel": by_channel
    }

if __name__ == "__main__":
    get_epg_data()
