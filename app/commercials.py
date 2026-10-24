"""Commercial detection for recordings, run on this PC in the background.

One FFmpeg pass reads the recording from the Tablo (gently) and gives, per recording: black frames
(blackdetect) and silences (silencedetect), which together mark the edges of commercial breaks; the
channel's corner, every second; and a tiny frame every second, turned into a colour histogram.

The corner comes first. US networks keep their logo (the FOX, CBS or NBC "bug") in the bottom-right
corner through the show and take it off for the ads, so a minute or more without it is a break, with
its edges snapped to the black-and-silent moment where the show stops and starts. On a Hell's Kitchen
recording this found all five breaks to within 10 s (3-4.5 minutes each), where the colour method
below found 47 s of two of them: the kitchen looks too much like ads.

Channels without a corner logo fall back to colour: a show looks like itself (Jeopardy's blue set, a
sitcom's sets) while ads look like anything else, so each second is scored by how much it looks like
the show; long runs that don't are breaks, with their edges snapped to nearby black frames.

Built to skip too little rather than too much: on a Jeopardy recording, show parts scored 0.57-0.60 and
every ad part 0.14-0.24, and all four breaks were found. On The Price Is Right (a colourful set that
looks a lot like ads) 6 of 9 breaks were found and no edge reached into the show; the others were
missed. When a recording's show and ads don't separate clearly at all, nothing is marked.
"""

import asyncio
import os
import re
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union

from . import childproc
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
MAX_AD_PIECE_SECONDS = 300  # between two black-and-silent moments: longer than this is show
SHORT_PIECE_SECONDS = 45
AD_PIECE_SHARE = 0.85  # a piece averaging below this share of the show's long pieces is ads
LEVEL_SECONDS = 0.05  # the sound's loudness is measured this often (speech dips between syllables)

# The detector, saved with each result: results from an older one are redone (1: colour only;
# 2: the channel logo, black frames and silences)
METHOD = 2

# The channel logo: the bottom-right corner of a 160x90 copy of each second's frame (the logo is a few
# pixels of light text there, still clear at that size)
FRAME_W, FRAME_H = 160, 90
CORNER_W, CORNER_H = 36, 22
LIGHTER = 12  # a logo pixel is this much lighter than the 5x5 around it, whatever the picture
LOGO_MIN_PIXELS = 12  # fewer pixels than this that are lighter most of the time: no logo to go by
LOGO_SEPARATION = 0.3  # seconds with and without the logo must score at least this far apart
LOGO_SMOOTH_SECONDS = 9
LOGO_MERGE_GAP = 35  # a network promo with the logo on (15-30 s), inside a break, doesn't split it
LOGO_SNAP_SECONDS = 12  # move a break edge to a black-and-silent moment (or a black frame) this close
# The logo comes back this long after the show does: Fox shows its TV rating badge instead for the
# first seconds back (Hell's Kitchen: 15-16 s after each of four breaks). If a channel brings it back
# at once, the cost is a few seconds of ad left in, not show skipped
LOGO_RETURN_LAG = 15


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


def loudness(ffmpeg_log: str) -> List[float]:
    """The sound's level (dB) every LEVEL_SECONDS, in order, from astats/ametadata in the log."""
    return [float(v) if v not in ("-inf", "nan") else -120.0
            for v in re.findall(r"lavfi\.astats\.Overall\.RMS_level=(\S+)", ffmpeg_log)]


def silences(ffmpeg_log: str) -> List[Tuple[float, float]]:
    """(start, end) of the silences FFmpeg's silencedetect reported, in seconds."""
    return [(float(a), float(b)) for a, b in
            re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", ffmpeg_log)]


def lighter_pixels(corner: bytes) -> List[bool]:
    """Which pixels of a grey CORNER_W x CORNER_H corner are clearly lighter than the 5x5 around them."""
    w, h = CORNER_W, CORNER_H
    # Sums of every rectangle from the top left, so each 5x5 average is four lookups
    sat = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        row = 0
        for x in range(w):
            row += corner[y * w + x]
            sat[y + 1][x + 1] = sat[y][x + 1] + row
    out = []
    for y in range(h):
        y0, y1 = max(0, y - 2), min(h, y + 3)
        for x in range(w):
            x0, x1 = max(0, x - 2), min(w, x + 3)
            total = sat[y1][x1] - sat[y0][x1] - sat[y1][x0] + sat[y0][x0]
            out.append(corner[y * w + x] - total / ((y1 - y0) * (x1 - x0)) > LIGHTER)
    return out


def logo_scores(corners: List[Union[bytes, Sequence[bool]]]) -> Optional[Tuple[List[float], float, float]]:
    """Per second, how much the channel's logo is in this corner, the score that separates "on"
    from "off", and how clearly they separate; None if there's no logo here to go by. A corner is
    its grey pixels, or already which of them are lit (lighter_pixels; the test recordings keep that)."""
    marks = [lighter_pixels(c) if isinstance(c, (bytes, bytearray)) else c for c in corners]
    n = len(marks)
    if n < 120:
        return None
    freq = [sum(m[i] for m in marks) / n for i in range(len(marks[0]))]
    logo = [i for i, f in enumerate(freq) if f > 0.5]  # light in most seconds: the logo
    rest = [i for i, f in enumerate(freq) if f < 0.2]  # the picture
    if len(logo) < LOGO_MIN_PIXELS or not rest:
        return None
    # Logo pixels lit, beyond what a busy picture lights everywhere anyway
    scores = [sum(m[i] for i in logo) / len(logo) - sum(m[i] for i in rest) / len(rest) for m in marks]
    t, lo, hi = _threshold(scores)
    # A QR code in an ad's corner can pass for the logo (about two thirds of its pixels lit); a
    # stricter cut-off would lose the logo over bright scenes too, so LOGO_MERGE_GAP bridges such ads
    return (scores, t, hi - lo) if hi - lo >= LOGO_SEPARATION else None


def best_logo(corners: List[Sequence[bytes]]) -> Optional[Tuple[List[float], float]]:
    """The corner with the channel's logo (most networks: bottom right; some channels use another)."""
    found = [logo_scores([c[k] for c in corners]) for k in range(len(corners[0]))]
    found = [f for f in found if f]
    if not found:
        return None
    scores, t, _ = max(found, key=lambda f: f[2])
    return scores, t


def _logo_breaks(scores: List[float], t: float, edges: List[float], blacks: List[float]) -> List[Dict[str, float]]:
    """Breaks from the seconds without the logo; edges are the black-and-silent moments."""
    n = len(scores)
    on = [s >= t for s in scores]
    half = LOGO_SMOOTH_SECONDS // 2
    smooth = [sum(on[max(0, i - half):i + half + 1]) * 2 > len(on[max(0, i - half):i + half + 1]) for i in range(n)]
    merged: List[List[int]] = []
    for s, e in _runs([not x for x in smooth]):
        if merged and s - merged[-1][1] <= LOGO_MERGE_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    def snap(t: float, marks: List[float]) -> Optional[float]:
        near = [b for b in marks if abs(b - t) <= LOGO_SNAP_SECONDS]
        return min(near, key=lambda b: abs(b - t)) if near else None

    breaks = []
    for s, e in merged:
        if e - s < MIN_BREAK_SECONDS:
            continue
        if s == 0 or e == n:
            # At the start or end of the recording: the show's own opening and closing often run
            # without the logo too, so only up to (from) the last (first) black-and-silent moment
            inside = [b for b in edges if s <= b <= e]
            if not inside:
                continue
            start, end = (0.0, max(inside)) if s == 0 else (min(inside), float(n))
            if end - start >= 10:
                breaks.append({"start": round(start, 1), "end": round(end, 1)})
            continue
        start = snap(float(s), edges) or snap(float(s), blacks)
        start = float(s) + 1 if start is None else start
        # The show was back LOGO_RETURN_LAG before the logo: end at the black frame there
        back = float(e) - LOGO_RETURN_LAG
        end = snap(back, blacks)
        end = back if end is None else end
        if end - start >= MIN_BREAK_SECONDS:
            breaks.append({"start": round(start, 1), "end": round(end, 1)})
    return breaks


def find_breaks(hists: List[List[float]], blacks: List[float], corners: Optional[List[Sequence[bytes]]] = None,
                quiet: Optional[List[Tuple[float, float]]] = None) -> Optional[List[Dict[str, float]]]:
    """Commercial breaks as [{'start', 'end'}] in seconds, or None if this recording's show and ads
    can't be told apart reliably. corners and quiet (silences) are used when there are any: the
    channel logo, edges at black frames that are also silent."""
    edges = sorted(b for b in blacks if any(a - 1 <= b <= z + 1 for a, z in quiet)) if quiet else sorted(blacks)
    if corners:
        found = best_logo([(c,) if isinstance(c, bytes) else c for c in corners])
        if found:
            return _logo_breaks(found[0], found[1], edges, sorted(blacks))
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
    if quiet:
        breaks = _join(breaks + _marked_pieces(scores, t, edges, n))
    return breaks


def _marked_pieces(scores: List[float], t: float, edges: List[float], n: int) -> List[Dict[str, float]]:
    """Without a logo: the black-and-silent moments mark nearly every break edge and the changes
    between ads (on a Price Is Right recording, 14 of 16 edges and almost nothing in the show), so
    the pieces between them that look like ads on average are ads. One second at a time, the show's
    colourful set and the ads overlap; a piece's average doesn't (ads 0.12-0.42, show 0.47-0.62)."""
    cuts: List[float] = []
    for b in [0.0] + edges + [float(n)]:
        if not cuts or b - cuts[-1] > 5:
            cuts.append(b)
    spans = list(zip(cuts, cuts[1:]))
    means = [sum(scores[int(a):max(int(b), int(a) + 1)]) / max(1, len(scores[int(a):max(int(b), int(a) + 1)])) for a, b in spans]
    # What the show's pieces look like: no break runs past MAX_AD_PIECE_SECONDS, so the long pieces
    # are show. A piece clearly below them is ads (Boston Blue: show 0.67-0.74, two whole breaks
    # 0.56-0.57, above the recording-wide cut-off). Without long pieces, that cut-off
    long_means = sorted(m for (a, b), m in zip(spans, means) if b - a > MAX_AD_PIECE_SECONDS)
    cut = long_means[len(long_means) // 2] * AD_PIECE_SHARE if long_means else t
    ad = [b - a <= MAX_AD_PIECE_SECONDS and m < cut for (a, b), m in zip(spans, means)]
    # A short piece against an ad piece is the rest of that break (an ad brighter than most): the
    # show never runs that briefly between two of these moments
    for i, (a, b) in enumerate(spans):
        if not ad[i] and b - a <= SHORT_PIECE_SECONDS and ((i and ad[i - 1]) or (i + 1 < len(ad) and ad[i + 1])):
            ad[i] = True
    return [{"start": round(a, 1), "end": round(b, 1)} for (a, b), x in zip(spans, ad) if x]


def _join(breaks: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Overlapping or touching breaks as one, in order."""
    out: List[Dict[str, float]] = []
    for b in sorted(breaks, key=lambda x: x["start"]):
        if out and b["start"] <= out[-1]["end"] + 1:
            out[-1]["end"] = max(out[-1]["end"], b["end"])
        else:
            out.append(dict(b))
    return [b for b in out if b["end"] - b["start"] >= 10]


# ---------------------------------------------------------------------------------------------------
# Background analysis of recordings from the shows it's turned on for (settings "commercial_shows")
# ---------------------------------------------------------------------------------------------------
# Read the recording at 4x real time: a 30-minute show takes about 8 minutes, without hurrying the
# Tablo (it serves this like someone watching)
READ_RATE = 4
WORKER_INTERVAL = 30
# Below normal priority: Windows process class, nice 10 elsewhere
LOW_PRIORITY = (0x00004000 | subprocess.CREATE_NO_WINDOW) if sys.platform == "win32" else 0
LOW_PRIORITY_POSIX = None if sys.platform == "win32" else (lambda: os.nice(10))

# The recording being analyzed: {"current": episode id, "title", "done": seconds read, "total", "started"}
status: Dict[str, object] = {"current": None}
_summary_cache: Dict[str, object] = {"at": 0.0, "value": None}


def enabled_shows() -> List[str]:
    return list(load_settings().get("commercial_shows") or [])


def set_show(show_id: str, on: bool) -> List[str]:
    shows = [s for s in enabled_shows() if s != show_id] + ([show_id] if on else [])
    save_settings({"commercial_shows": shows})
    return shows


def queued_episodes() -> List[str]:
    """Single recordings asked for from the episode menu (whatever their show's setting)."""
    return list(load_settings().get("commercial_episodes") or [])


def queue_episode(episode_id: str) -> None:
    save_settings({"commercial_episodes": [e for e in queued_episodes() if e != episode_id] + [episode_id]})


def pending(shows: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Finished recordings not analyzed yet: single ones asked for first, then the unwatched ones of
    the enabled shows, newest first."""
    shows = enabled_shows() if shows is None else shows
    queued = queued_episodes()
    if not shows and not queued:
        return []
    marks = ",".join("?" * len(shows)) or "''"
    qmarks = ",".join("?" * len(queued)) or "''"
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT e.id, e.path, e.show_id, e.show_title, e.season_number, e.episode_number, e.duration, e.raw_json
            FROM episodes e
            LEFT JOIN commercials c ON c.episode_id = e.id
            WHERE (c.episode_id IS NULL
                   -- found by an older detector: again (it kept the old breaks meanwhile), unless watched
                   OR (COALESCE(c.method, 1) < {METHOD} AND c.status IN ('done', 'unreliable') AND e.status != 'Watched'))
              AND (e.id IN ({qmarks}) OR (e.show_id IN ({marks}) AND e.status != 'Watched'))
            ORDER BY e.air_date DESC
        """, [*queued, *shows]).fetchall()
    found = []
    for r in rows:
        details = recording_details(r["raw_json"])
        if details["recording_state"] == "finished":
            se = f" S{r['season_number']}E{r['episode_number']}" if r["season_number"] and r["episode_number"] else ""
            found.append({"id": r["id"], "path": r["path"], "show_id": r["show_id"], "show_title": r["show_title"],
                          "title": f"{r['show_title']}{se}", "duration": details["actual_duration"] or r["duration"] or 0})
    return sorted(found, key=lambda ep: ep["id"] not in queued)  # stable: keeps newest first within each


def summary() -> Optional[Dict[str, object]]:
    """For the status line: what the commercial finder is doing, or None when it has nothing to do.
    state: running (with percent and minutes_left), paused (something is playing) or waiting."""
    if status.get("current"):
        total = float(status.get("total") or 0)
        done = float(status.get("done") or 0)
        elapsed = time.time() - float(status.get("started") or time.time())
        left = (total - done) / (done / elapsed) / 60 if done > 30 and elapsed > 0 and total > done else None
        return {"state": "running", "episode_id": status["current"], "title": status.get("title"),
                "percent": min(99, round(done / total * 100)) if total else None,
                "minutes_left": max(1, round(left)) if left else None,
                "waiting": max(0, len(_cached_pending()) - 1)}
    queue = _cached_pending()
    if not queue:
        return None
    return {"state": "paused" if _busy() else "waiting", "waiting": len(queue)}


def _cached_pending() -> List[Dict[str, str]]:
    """pending(), at most every 15 s (the status line asks every few seconds)."""
    if time.time() - float(_summary_cache["at"]) > 15:
        _summary_cache["value"] = pending() if (enabled_shows() or queued_episodes()) else []
        _summary_cache["at"] = time.time()
    return _summary_cache["value"] or []


def _busy() -> bool:
    """Something is playing or exporting: analysis waits (it would compete for the Tablo and the PC)."""
    from .transcode import transcode_manager
    return bool(transcode_manager.sessions) or any(not t.done() for t in transcode_manager.export_tasks.values())


# Each second FFmpeg sends one OUT_W x OUT_H rgb24 frame: the colour thumbnail on top (padded to the
# corners' width) and the four grey corners below it, in CORNERS order
CORNERS = ("top left", "top right", "bottom left", "bottom right")
OUT_W, OUT_H = CORNER_W, THUMB_H + len(CORNERS) * CORNER_H


def analysis_graph() -> str:
    """FFmpeg's filter graph for the one pass: [bd] black frames, [o] the per-second frame, [sd]
    silences and [lv] loudness every LEVEL_SECONDS (the last three printed to the log)."""
    x, y = FRAME_W - CORNER_W, FRAME_H - CORNER_H
    crops = [(0, 0), (x, 0), (0, y), (x, y)]
    labels = "".join(f"[k{i}]" for i in range(len(crops)))
    return (f"[0:v]scale=320:-2,split[a][b];[a]blackdetect=d=0.05:pix_th=0.10[bd];"
            f"[b]fps=1,scale={FRAME_W}:{FRAME_H},format=rgb24,split={len(crops) + 1}[p]{labels};"
            f"[p]scale={THUMB_W}:{THUMB_H},pad={OUT_W}:{THUMB_H}[t];"
            + "".join(f"[k{i}]crop={CORNER_W}:{CORNER_H}:{cx}:{cy},format=gray,format=rgb24[c{i}];" for i, (cx, cy) in enumerate(crops))
            + "[t]" + "".join(f"[c{i}]" for i in range(len(crops))) + f"vstack=inputs={len(crops) + 1},format=rgb24[o];"
            f"[0:a]asplit[a1][a2];[a1]silencedetect=n=-50dB:d=0.15[sd];"
            f"[a2]aformat=sample_rates=8000:channel_layouts=mono,asetnsamples=n={int(8000 * LEVEL_SECONDS)}:p=0,"
            f"astats=metadata=1:reset=1:measure_overall=RMS_level:measure_perchannel=none,"
            f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level[lv]")


def _split_frame(frame: bytes) -> Tuple[bytes, Tuple[bytes, ...]]:
    """(the THUMB_W x THUMB_H rgb24 thumbnail, the grey corners) from one FFmpeg frame."""
    row = OUT_W * 3
    thumb = b"".join(frame[y * row:y * row + THUMB_W * 3] for y in range(THUMB_H))
    corners = tuple(bytes(frame[(THUMB_H + k * CORNER_H + y) * row + x * 3] for y in range(CORNER_H) for x in range(CORNER_W))
                    for k in range(len(CORNERS)))
    return thumb, corners


def _analyze(url: str, log_path, stop: threading.Event, progress: Optional[Dict[str, object]] = None) -> Optional[Tuple[List[List[float]], List[Tuple[bytes, ...]]]]:
    """One FFmpeg pass: black frames, silences and loudness to the log, and per second a colour
    histogram and the four corners to us. None if stopped."""
    cmd = [FFMPEG_PATH, "-hide_banner", "-nostats", "-readrate", str(READ_RATE), "-i", url,
           "-filter_complex", analysis_graph(),
           "-map", "[bd]", "-f", "null", "-",
           "-map", "[sd]", "-f", "null", "-",
           "-map", "[lv]", "-f", "null", "-",
           "-map", "[o]", "-f", "rawvideo", "-"]
    size = OUT_W * OUT_H * 3
    hists: List[List[float]] = []
    corners: List[Tuple[bytes, ...]] = []
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, creationflags=LOW_PRIORITY,
                                **childproc.popen_kwargs(LOW_PRIORITY_POSIX))
        childproc.tie_to_app(proc)
        watcher = threading.Thread(target=lambda: (stop.wait(), proc.poll() is None and proc.kill()), daemon=True)
        watcher.start()
        try:
            while True:
                frame = proc.stdout.read(size)
                if len(frame) < size:
                    break
                thumb, corner = _split_frame(frame)
                hists.append(histogram(thumb))
                corners.append(corner)
                if progress is not None:
                    progress["done"] = len(hists)
            proc.wait()
        finally:
            stop.set()
    if proc.returncode != 0 and not hists:
        raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")
    return None if proc.returncode != 0 and len(hists) < 60 else (hists, corners)


async def analyze(ep: Dict[str, str]) -> Optional[str]:
    """Find the breaks in one recording and save them. Returns the status, or None if it was
    interrupted (something started playing) and should be tried again later."""
    from .tablo_client import tablo_manager
    url = (await tablo_manager.get_airing_watch_url(ep["path"])).get("playlist_url")
    if not url:
        raise RuntimeError("the Tablo didn't return a stream")
    log_path = TRANSCODE_DIR / f"ads_{ep['id']}.log"
    stop = threading.Event()
    job = asyncio.get_running_loop().run_in_executor(None, _analyze, url, log_path, stop, status)
    while not job.done():
        await asyncio.sleep(2)
        if _busy():
            stop.set()
            await job
            return None
    result = await job
    if result is None:
        return None
    hists, corners = result
    try:
        log = log_path.read_text(encoding="utf-8", errors="replace")
    finally:
        log_path.unlink(missing_ok=True)
    breaks = find_breaks(hists, black_frames(log), corners, silences(log))
    save_commercials(ep["id"], "unreliable" if breaks is None else "done", breaks, method=METHOD)
    print(f"[Commercials] {ep['show_title']} {ep['id']}: "
          f"{'show and ads could not be told apart' if breaks is None else f'{len(breaks)} breaks'}")
    return "unreliable" if breaks is None else "done"


async def worker_loop() -> None:
    """Every minute: if nothing is playing, analyze the next waiting recording."""
    from .tablo_client import tablo_manager
    while True:
        await asyncio.sleep(WORKER_INTERVAL)
        try:
            from . import dropouts  # one background read of a recording from the Tablo at a time
            if not tablo_manager.is_authenticated or _busy() or dropouts.status.get("current"):
                continue
            queue = await asyncio.to_thread(pending)
            if not queue:
                continue
            ep = queue[0]
            status.update(current=ep["id"], title=ep["title"], done=0, total=ep["duration"], started=time.time())
            try:
                await analyze(ep)
            except Exception as e:
                print(f"[Commercials] Couldn't analyze {ep['show_title']} {ep['id']}: {e}")
                save_commercials(ep["id"], "failed", error=str(e)[:300])
            finally:
                status["current"] = None
                _summary_cache["at"] = 0.0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Commercials] {e}")
