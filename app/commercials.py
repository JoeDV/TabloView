"""Commercial detection for recordings, run on this PC in the background.

One FFmpeg pass reads the recording from the Tablo (gently) and gives two things per recording: black
frames (blackdetect; broadcasters put them at the edges of commercial breaks) and a tiny frame every
second, turned into a colour histogram. A show looks like itself (Jeopardy's blue set, a sitcom's
sets) while ads look like anything else, so each second is scored by how much it looks like the
show; long runs that don't are breaks, with their edges snapped to nearby black frames.

Built to skip too little rather than too much: on a Jeopardy recording, show parts scored 0.57-0.60 and
every ad part 0.14-0.24, and all four breaks were found. On The Price Is Right (a colourful set that
looks a lot like ads) 6 of 9 breaks were found and no edge reached into the show; the others were
missed. When a recording's show and ads don't separate clearly at all, nothing is marked.
"""

import asyncio
import re
import subprocess
import sys
import threading
from typing import Dict, List, Optional, Sequence, Tuple

from .config import FFMPEG_PATH, TRANSCODE_DIR
from .database import get_connection, save_commercials, recording_details
from .settings import load_settings, save_settings

THUMB_W, THUMB_H = 32, 18  # the per-second frame size (rgb24)
BINS = 64  # 4 levels each of red, green and blue
SMOOTH_SECONDS = 15  # majority vote over this window evens out single odd frames
# US commercial breaks run a minute or more; shorter odd-looking stretches are the show's own graphics
# (e.g. Jeopardy's red Final Jeopardy reveal, 25 s)
MIN_BREAK_SECONDS = 45
MERGE_GAP_SECONDS = 10  # a moment of show-like frames inside a break doesn't split it
SNAP_SECONDS = 8  # move a break edge to a black frame this close
# An edge without a black frame to anchor it moves this far into the break: better a few seconds of
# ad than skipping any of the show (what Tablo's own commercial skip got wrong)
UNANCHORED_TRIM = 3
MIN_SEPARATION = 0.15  # show and ad scores must be at least this far apart to trust the result


def histogram(frame: bytes) -> List[float]:
    """64-bin colour histogram of one rgb24 frame, as fractions of the pixels."""
    h = [0] * BINS
    for p in range(0, len(frame) - 2, 3):
        h[(frame[p] >> 6) * 16 + (frame[p + 1] >> 6) * 4 + (frame[p + 2] >> 6)] += 1
    total = len(frame) // 3 or 1
    return [x / total for x in h]


def black_frames(ffmpeg_log: str) -> List[float]:
    """Midpoints of the black frames FFmpeg's blackdetect reported, in seconds."""
    return [(float(a) + float(b)) / 2
            for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", ffmpeg_log)]


def _mean(hs: Sequence[List[float]]) -> List[float]:
    n = len(hs) or 1
    return [sum(h[k] for h in hs) / n for k in range(BINS)]


def _similarity(a: List[float], b: List[float]) -> float:
    return sum(min(x, y) for x, y in zip(a, b))


def _threshold(values: List[float]) -> Tuple[float, float, float]:
    """Split values into two groups (1-D k-means): (threshold, low centre, high centre)."""
    lo, hi = min(values), max(values)
    for _ in range(20):
        t = (lo + hi) / 2
        low = [v for v in values if v < t] or [lo]
        high = [v for v in values if v >= t] or [hi]
        lo, hi = sum(low) / len(low), sum(high) / len(high)
    return (lo + hi) / 2, lo, hi


def _runs(flags: List[bool]) -> List[Tuple[int, int]]:
    """[start, end) index ranges where flags is True."""
    runs, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i))
            start = None
    return runs


def find_breaks(hists: List[List[float]], blacks: List[float]) -> Optional[List[Dict[str, float]]]:
    """Commercial breaks as [{'start', 'end'}] in seconds, or None if this recording's show and ads
    can't be told apart reliably."""
    n = len(hists)
    if n < 120:
        return None
    # What the show looks like: start from the longest stretch between black frames (almost always
    # show), then refine from every second that matched it
    cuts = [0.0] + sorted(blacks) + [float(n)]
    a, b = max(zip(cuts, cuts[1:]), key=lambda s: s[1] - s[0])
    ref = _mean(hists[int(a):max(int(b), int(a) + 1)])
    for _ in range(2):
        scores = [_similarity(h, ref) for h in hists]
        t, lo, hi = _threshold(scores)
        ref = _mean([h for h, s in zip(hists, scores) if s >= t])
    if hi - lo < MIN_SEPARATION:
        return None

    show = [s >= t for s in scores]
    half = SMOOTH_SECONDS // 2
    smooth = [sum(show[max(0, i - half):i + half + 1]) * 2 > len(show[max(0, i - half):i + half + 1])
              for i in range(n)]
    ads = _runs([not s for s in smooth])
    merged: List[List[int]] = []
    for s, e in ads:
        if merged and s - merged[-1][1] <= MERGE_GAP_SECONDS:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    def snap(t: float) -> Optional[float]:
        near = [b for b in blacks if abs(b - t) <= SNAP_SECONDS]
        return min(near, key=lambda b: abs(b - t)) if near else None

    breaks = []
    for s, e in merged:
        if e - s < MIN_BREAK_SECONDS:
            continue
        start, end = snap(float(s)), snap(float(e))
        # A real break has a black frame at one edge at least (or runs to the start or end of the recording)
        if start is None and end is None and 0 < s and e < n:
            continue
        start = float(s) + UNANCHORED_TRIM if start is None else start
        end = float(e) - UNANCHORED_TRIM if end is None else end
        breaks.append({"start": round(start if s > 0 else 0.0, 1), "end": round(end if e < n else float(n), 1)})
    return breaks


# ---------------------------------------------------------------------------------------------------
# Background analysis of recordings from the shows it's turned on for (settings "commercial_shows")
# ---------------------------------------------------------------------------------------------------
# Read the recording at 4x real time: a 30-minute show takes about 8 minutes, without hurrying the
# Tablo (it serves this like someone watching)
READ_RATE = 4
WORKER_INTERVAL = 60
LOW_PRIORITY = (0x00004000 | subprocess.CREATE_NO_WINDOW) if sys.platform == "win32" else 0  # below normal

status: Dict[str, Optional[str]] = {"current": None}


def enabled_shows() -> List[str]:
    return list(load_settings().get("commercial_shows") or [])


def set_show(show_id: str, on: bool) -> List[str]:
    shows = [s for s in enabled_shows() if s != show_id] + ([show_id] if on else [])
    save_settings({"commercial_shows": shows})
    return shows


def pending(shows: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Unwatched, finished recordings of the enabled shows not analyzed yet, newest first."""
    shows = enabled_shows() if shows is None else shows
    if not shows:
        return []
    marks = ",".join("?" * len(shows))
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT e.id, e.path, e.show_id, e.show_title, e.raw_json FROM episodes e
            LEFT JOIN commercials c ON c.episode_id = e.id
            WHERE e.show_id IN ({marks}) AND e.status != 'Watched' AND c.episode_id IS NULL
            ORDER BY e.air_date DESC
        """, shows).fetchall()
    return [{"id": r["id"], "path": r["path"], "show_id": r["show_id"], "show_title": r["show_title"]}
            for r in rows if recording_details(r["raw_json"])["recording_state"] == "finished"]


def _busy() -> bool:
    """Something is playing or exporting: analysis waits (it would compete for the Tablo and the PC)."""
    from .transcode import transcode_manager
    return bool(transcode_manager.sessions) or any(not t.done() for t in transcode_manager.export_tasks.values())


def _analyze(url: str, log_path, stop: threading.Event) -> Optional[List[List[float]]]:
    """One FFmpeg pass: black frames to the log, a tiny frame per second to us. None if stopped."""
    cmd = [FFMPEG_PATH, "-hide_banner", "-nostats", "-readrate", str(READ_RATE), "-i", url,
           "-filter_complex",
           f"[0:v]scale=320:-2,split[a][b];[a]blackdetect=d=0.05:pix_th=0.10[bd];"
           f"[b]fps=1,scale={THUMB_W}:{THUMB_H},format=rgb24[t]",
           "-map", "[bd]", "-f", "null", "-",
           "-map", "[t]", "-f", "rawvideo", "-"]
    size = THUMB_W * THUMB_H * 3
    hists: List[List[float]] = []
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, creationflags=LOW_PRIORITY)
        watcher = threading.Thread(target=lambda: (stop.wait(), proc.poll() is None and proc.kill()), daemon=True)
        watcher.start()
        try:
            while True:
                frame = proc.stdout.read(size)
                if len(frame) < size:
                    break
                hists.append(histogram(frame))
            proc.wait()
        finally:
            stop.set()
    if proc.returncode != 0 and not hists:
        raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")
    return None if proc.returncode != 0 and len(hists) < 60 else hists


async def analyze(ep: Dict[str, str]) -> Optional[str]:
    """Find the breaks in one recording and save them. Returns the status, or None if it was
    interrupted (something started playing) and should be tried again later."""
    from .tablo_client import tablo_manager
    url = (await tablo_manager.get_airing_watch_url(ep["path"])).get("playlist_url")
    if not url:
        raise RuntimeError("the Tablo didn't return a stream")
    log_path = TRANSCODE_DIR / f"ads_{ep['id']}.log"
    stop = threading.Event()
    job = asyncio.get_running_loop().run_in_executor(None, _analyze, url, log_path, stop)
    while not job.done():
        await asyncio.sleep(2)
        if _busy():
            stop.set()
            await job
            return None
    hists = await job
    if hists is None:
        return None
    try:
        log = log_path.read_text(encoding="utf-8", errors="replace")
    finally:
        log_path.unlink(missing_ok=True)
    breaks = find_breaks(hists, black_frames(log))
    save_commercials(ep["id"], "unreliable" if breaks is None else "done", breaks)
    print(f"[Commercials] {ep['show_title']} {ep['id']}: "
          f"{'show and ads could not be told apart' if breaks is None else f'{len(breaks)} breaks'}")
    return "unreliable" if breaks is None else "done"


async def worker_loop() -> None:
    """Every minute: if nothing is playing, analyze the next waiting recording."""
    from .tablo_client import tablo_manager
    while True:
        await asyncio.sleep(WORKER_INTERVAL)
        try:
            if not tablo_manager.is_authenticated or _busy():
                continue
            queue = await asyncio.to_thread(pending)
            if not queue:
                continue
            ep = queue[0]
            status["current"] = ep["id"]
            try:
                await analyze(ep)
            except Exception as e:
                print(f"[Commercials] Couldn't analyze {ep['show_title']} {ep['id']}: {e}")
                save_commercials(ep["id"], "failed", error=str(e)[:300])
            finally:
                status["current"] = None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Commercials] {e}")
