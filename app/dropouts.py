"""Signal dropouts in recordings: the stretches where a weak signal left the picture broken or missing,
found so the player can mark them (in red, beside the commercial breaks) and skip them.

Only recordings the Tablo itself flags as not clean (video_details.clean = false) are read, once each,
in the background when nothing is playing, like the commercial finder (about a CPU core, at 4x: a
one-hour recording takes 15 minutes). The status line shows it, and Settings → Playback turns it off
(setting "find_dropouts"; a forum user on Linux saw FFmpeg running for hours with nothing saying why). FFmpeg decodes the recording
(no output) and the same signs as the live signal meter (app/reception.py) are mapped onto the
recording's own timeline: frames thrown away or patched over, and jumps in the timeline where frames
never arrived.
"""

import asyncio
import json
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import childproc
from .commercials import LOW_PRIORITY, LOW_PRIORITY_POSIX, READ_RATE, _busy, _busy_with
from .config import FFMPEG_PATH, TRANSCODE_DIR
from .database import get_connection, recording_details
from .settings import load_settings

WORKER_INTERVAL = 45
STALL_SECONDS = 60  # no progress for this long: the Tablo stopped sending; keep what was found
MIN_READ_SECONDS = 60  # stalled before reading this much: "couldn't read it", not "no dropouts"
DAMAGED_SHARE = 0.2  # a stretch counts as a dropout when this much of its picture didn't arrive intact
MERGE_GAP = 3.0  # dropouts closer than this become one (a flicker of good picture isn't worth stopping for)
PAD = 1.0  # seconds added either side, so a skip lands on clean picture
MIN_LENGTH = 1.5  # shorter blips aren't worth a mark

status: Dict[str, Any] = {"current": None}
_pending_cache: Dict[str, Any] = {"at": 0.0, "value": []}


def enabled() -> bool:
    return bool(load_settings().get("find_dropouts", True))

_PROGRESS = re.compile(r"frame=\s*(\d+).*?time=(\d+):(\d+):([\d.]+)")
_VIDEO = re.compile(r"Stream #0:(\d+)\S*: Video: .*?([\d.]+) fps")


def save(episode_id: str, state: str, spans: List[Dict[str, float]]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO dropouts (episode_id, status, spans_json, analyzed_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(episode_id) DO UPDATE SET status = excluded.status, spans_json = excluded.spans_json,
                analyzed_at = excluded.analyzed_at
        """, (episode_id, state, json.dumps(spans), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        conn.commit()


def get(episode_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM dropouts WHERE episode_id = ?", (episode_id,)).fetchone()
    return {"status": row["status"], "spans": json.loads(row["spans_json"] or "[]")} if row else None


def pending() -> List[Dict[str, Any]]:
    """Finished recordings the Tablo flagged as not clean, not read yet; newest first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.id, e.path, e.show_title, e.duration, e.raw_json FROM episodes e
            LEFT JOIN dropouts d ON d.episode_id = e.id
            WHERE d.episode_id IS NULL ORDER BY e.air_date DESC
        """).fetchall()
    out = []
    for r in rows:
        raw = json.loads(r["raw_json"] or "{}")
        vd = raw.get("video_details") or {}
        details = recording_details(r["raw_json"])
        # Finished ones only: the Tablo won't play a recording it marked failed ("404 Not Found" for
        # all three tried on 2026-10-20), so there's nothing to read, or to watch
        if vd.get("clean") is False and details["recording_state"] == "finished" \
                and (details["actual_duration"] or 0) > 60:
            out.append({"id": r["id"], "path": r["path"], "show_title": r["show_title"],
                        "duration": details["actual_duration"] or r["duration"] or 0})
    return out


def find_dropouts(log: str) -> List[Dict[str, float]]:
    """Dropout spans (recording seconds) from a decode-only FFmpeg log, in the order it was written.

    Between two progress lines FFmpeg covered (t0, t1] of the recording: damaged frames are the ones it
    threw away or patched; missing ones, the timeline it moved past without making frames."""
    m = _VIDEO.search(log)
    if not m:
        return []
    stream, fps = m.group(1), float(m.group(2))
    damage = re.compile(rf"Packet corrupt \(stream = {stream},|\[vist#0:{stream}/[^\]]*\] \[dec:[^\]]*\] corrupt decoded frame")
    bad: List[Tuple[float, float]] = []
    last: Optional[Tuple[int, float]] = None
    pending_damage = 0
    for line in re.split(r"[\r\n]+", log):
        if damage.search(line):
            pending_damage += 1
            continue
        p = _PROGRESS.search(line)
        if not p:
            continue
        frames, t = int(p.group(1)), int(p.group(2)) * 3600 + int(p.group(3)) * 60 + float(p.group(4))
        if last is None or t <= last[1]:
            last = (frames, max(t, last[1] if last else 0.0))
            pending_damage = 0 if last is None else pending_damage
            continue
        span = t - last[1]
        due = span * fps
        missing = max(0.0, due - (frames - last[0]))
        lost = min(due, pending_damage + missing)
        if due >= 1 and lost / due >= DAMAGED_SHARE:
            bad.append((last[1], t))
        last, pending_damage = (frames, t), 0
    spans: List[List[float]] = []
    for start, end in bad:
        if spans and start - spans[-1][1] <= MERGE_GAP:
            spans[-1][1] = end
        else:
            spans.append([start, end])
    return [{"start": round(max(0.0, s - PAD), 1), "end": round(e + PAD, 1)}
            for s, e in spans if e - s >= MIN_LENGTH]


def _decode(url: str, log_path, stop: threading.Event) -> str:
    """Decode the recording to nowhere, at READ_RATE, low priority; stops when stop is set or when no
    progress has been logged for STALL_SECONDS. Returns 'done' or 'stalled'."""
    cmd = [FFMPEG_PATH, "-hide_banner", "-fflags", "+discardcorrupt", "-readrate", str(READ_RATE), "-i", url,
           "-map", "0:v:0", "-f", "null", "-", "-stats_period", "1"]
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log, creationflags=LOW_PRIORITY,
                                **childproc.popen_kwargs(LOW_PRIORITY_POSIX))
    childproc.tie_to_app(proc)
    size, changed = 0, time.monotonic()
    while proc.poll() is None:
        if stop.wait(2):
            proc.kill()
            proc.wait()
            return "stopped"
        now_size = log_path.stat().st_size if log_path.exists() else 0
        if now_size != size:
            size, changed = now_size, time.monotonic()
        elif time.monotonic() - changed > STALL_SECONDS:
            proc.kill()
            proc.wait()
            return "stalled"
    return "done"


async def analyze(ep: Dict[str, Any]) -> Optional[str]:
    """Find the dropouts in one recording and save them; None if interrupted (something started playing)."""
    from .tablo_client import tablo_manager
    print(f"[Dropouts] Checking {ep['show_title']} {ep['id']} for signal dropouts (the Tablo flagged it as not clean;"
          f" {len(_cached_pending()) - 1} more waiting)")
    try:
        url = (await tablo_manager.get_airing_watch_url(ep["path"])).get("playlist_url")
    except Exception as e:
        print(f"[Dropouts] {ep['show_title']} {ep['id']}: couldn't open it on the Tablo ({e})")
        save(ep["id"], "unavailable", [])
        return "unavailable"
    log_path = TRANSCODE_DIR / f"dropouts_{ep['id']}.log"
    stop = threading.Event()
    status.update(current=ep["id"], title=ep["show_title"], total=ep.get("duration") or 0, started=time.time(),
                  log=log_path)
    try:
        job = asyncio.get_running_loop().run_in_executor(None, _decode, url, log_path, stop)
        while not job.done():
            await asyncio.sleep(2)
            if _busy() or not enabled():
                stop.set()
                await job
                return None
        result = await job
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    finally:
        status["current"] = None
        _pending_cache["at"] = 0.0
        log_path.unlink(missing_ok=True)
    spans = find_dropouts(log)
    read = seconds_read(log)
    if result == "stalled" and read < MIN_READ_SECONDS:
        # Nothing to go on: "no dropouts" would be wrong (The Voice, 2026-10-13: the picture is too
        # damaged at the start for FFmpeg to begin, and the Tablo stopped sending)
        save(ep["id"], "unreadable", [])
        print(f"[Dropouts] {ep['show_title']} {ep['id']}: couldn't read it (stopped after {round(read)} s)")
        return "unreadable"
    save(ep["id"], "partial" if result == "stalled" else "done", spans)
    print(f"[Dropouts] {ep['show_title']} {ep['id']}: {len(spans)} dropout{'s' if len(spans) != 1 else ''}"
          f"{f' in the first {round(read / 60)} min (the Tablo stopped sending there)' if result == 'stalled' else ''}")
    return result


def _cached_pending() -> List[Dict[str, Any]]:
    """pending(), at most every 15 s (the status line asks every few seconds)."""
    if time.time() - float(_pending_cache["at"]) > 15:
        _pending_cache["value"] = pending()
        _pending_cache["at"] = time.time()
    return _pending_cache["value"]


def summary() -> Optional[Dict[str, Any]]:
    """For the status line: running (with percent and minutes_left), paused (something is playing or
    exporting), after_commercials (waits for the commercial finder) or waiting; None with nothing to do."""
    if not enabled():
        return None
    queue = _cached_pending()
    if status.get("current"):
        total = float(status.get("total") or 0)
        try:
            with open(status["log"], "rb") as f:
                f.seek(max(0, f.seek(0, 2) - 4096))
                done = seconds_read(f.read().decode("utf-8", "replace"))
        except (OSError, KeyError):
            done = 0.0
        elapsed = time.time() - float(status.get("started") or time.time())
        left = (total - done) / (done / elapsed) / 60 if done > 30 and elapsed > 0 and total > done else None
        return {"state": "running", "episode_id": status["current"], "title": status.get("title"),
                "percent": min(99, round(done / total * 100)) if total else None,
                "minutes_left": max(1, round(left)) if left else None,
                "waiting": max(0, len(queue) - 1)}
    if not queue:
        return None
    from . import commercials
    reason = _busy_with()
    state = "paused" if reason else "after_commercials" if commercials.status.get("current") else "waiting"
    return {"state": state, "reason": reason, "waiting": len(queue)}


def seconds_read(log: str) -> float:
    """How far into the recording FFmpeg got, from its last progress line."""
    found = _PROGRESS.findall(log)
    if not found:
        return 0.0
    _, h, m, s = found[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


async def worker_loop() -> None:
    """Every so often: if nothing is playing and the commercial finder is idle, read the next flagged recording."""
    from . import commercials
    from .tablo_client import tablo_manager
    while True:
        await asyncio.sleep(WORKER_INTERVAL)
        try:
            if not enabled() or not tablo_manager.is_authenticated or _busy() or commercials.status.get("current"):
                continue
            queue = await asyncio.to_thread(pending)
            if queue:
                await analyze(queue[0])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Dropouts] {e}")
