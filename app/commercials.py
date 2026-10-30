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
from pathlib import Path
import os
import re
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union

from . import childproc
from .config import DATA_DIR, FFMPEG_PATH, TRANSCODE_DIR
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
# A piece this short next to an ad piece is part of the same break, whatever it looks like: a dim
# one-minute drug ad opened a Tracker break and scored like the show (2026-10-25, 62 s). Raising this
# from 45 changed nothing on the five test recordings
SHORT_PIECE_SECONDS = 65
AD_PIECE_SHARE = 0.85  # a piece averaging below this share of the show's long pieces is ads
LEVEL_SECONDS = 0.05  # the sound's loudness is measured this often (speech dips between syllables)

# The detector, saved with each result: results from an older one are redone (1: colour only;
# 2: the channel logo, black frames and silences; 3: up to a minute of show-like ad next to a break;
# 4: a break ends where the show comes back, not a fixed time before the logo does). Not raised for
# _without_long_pieces (2026-10-30): every copy would re-read every unwatched recording, logo channels
# too; a show's recordings are redone on request instead (its page, or a recording's menu)
METHOD = 4

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
# ABC brings it back later still: 18-37 s after the show (Shark Tank, 2026-10-29; ending each break
# LOGO_RETURN_LAG before the logo skipped up to 22 s of the show). So a break ends at its last
# black-and-silent moment up to this long before the logo returns
LOGO_RETURN_MAX = 45
# A break has the logo gone for at least LOGO_SOLID_SECONDS in a row (ignoring blips of it of up to
# LOGO_BLIP_SECONDS). ABC's see-through logo dropped out for 5-10 s at a time on bright scenes, and
# 87 s of Shark Tank was taken for a break
LOGO_SOLID_SECONDS = 20
LOGO_BLIP_SECONDS = 1
# A faint logo: CBS's see-through eye is ~5 px wide in the 160x90 copy, too faint for the corners above
# (and lit in under half the seconds: it vanishes on bright scenes, and ads are a quarter of the time).
# In a 480x270 copy's corners (EYE_W x EYE_H) it's a clear ring. A pixel EYE_LIGHTER lighter than the
# 5x5 around it (worked out by FFmpeg) and lit in over EYE_PIXEL_SHARE of the seconds is the logo; at
# least EYE_MIN_PIXELS of them, or there's none; a second with EYE_ON of them lit has it on. On
# Survivor that's on in 91% of show seconds and 6% of ad seconds
EYE_SCALE_W, EYE_SCALE_H = 480, 270
EYE_W, EYE_H = 108, 66
EYE_LIGHTER = 8
EYE_PIXEL_SHARE = 0.35
EYE_MIN_PIXELS = 20
EYE_ON = 0.3
EYE_EDGE = 3
EYE_GONE_EARLY = 20  # a break starts at the first black frame this long after the eye goes
EYE_SAMPLE = 5  # which pixels are the logo: judged from every 5th second (the same answer, a fifth of the work)


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


def _logo_breaks(scores: List[float], t: float, edges: List[float], blacks: List[float],
                 nearest_start: bool = False) -> List[Dict[str, float]]:
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
    # Where the logo is gone for good (a second or two of it showing aside): a break has at least one
    # such stretch and its edges are at the first and last of them. A see-through logo (ABC) flickers
    # out on bright scenes in the show, which the smoothing alone took for breaks or joined onto them
    off = [not x for x in on]
    for s, e in _runs(on):
        if e - s <= LOGO_BLIP_SECONDS:
            off[s:e] = [True] * (e - s)
    solid = [r for r in _runs(off) if r[1] - r[0] >= LOGO_SOLID_SECONDS]
    trimmed = []
    for s, e in merged:
        inside = [r for r in solid if r[0] < e and r[1] > s]
        if inside:
            trimmed.append([max(s, inside[0][0]), min(e, inside[-1][1])])
    merged = trimmed

    def snap(t: float, marks: List[float]) -> Optional[float]:
        near = [b for b in marks if abs(b - t) <= LOGO_SNAP_SECONDS]
        return min(near, key=lambda b: abs(b - t)) if near else None

    def last_before(t: float, marks: List[float]) -> Optional[float]:
        near = [b for b in marks if t - LOGO_RETURN_MAX <= b <= t]
        return max(near) if near else None

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
        # The faint logo (nearest_start): CBS takes the eye off up to ~15 s before it cuts away (The Price
        # Is Right, 2026-10-30: gone at 35:48, black at 36:01), so the first black frame after it goes
        if nearest_start:
            after = [b for b in blacks if s - 2 <= b <= s + EYE_GONE_EARLY]
            start = min(after) if after else None
        else:
            start = snap(float(s), edges) or snap(float(s), blacks)
        start = float(s) + 1 if start is None else start
        # The show comes back before the logo does, at the break's last black frame (silent on ABC,
        # not always on Fox); without one, LOGO_RETURN_LAG before the logo
        end = last_before(float(e), blacks)
        if end is None or end <= start:
            back = float(e) - LOGO_RETURN_LAG
            end = snap(back, blacks)
            end = back if end is None else end
        if end - start >= MIN_BREAK_SECONDS:
            breaks.append({"start": round(start, 1), "end": round(end, 1)})
    return breaks


def find_breaks(hists: List[List[float]], blacks: List[float], corners: Optional[List[Sequence[bytes]]] = None,
                quiet: Optional[List[Tuple[float, float]]] = None,
                program_end: Optional[float] = None, how: Optional[Dict[str, str]] = None,
                eye: Optional[List[float]] = None) -> Optional[List[Dict[str, float]]]:
    """Commercial breaks as [{'start', 'end'}] in seconds, or None if this recording's show and ads
    can't be told apart reliably. corners and quiet (silences) are used when there are any: the
    channel logo, edges at black frames that are also silent. program_end: where the show is
    scheduled to end in the recording. eye: per second, how much of a faint logo is showing in a
    bigger corner (eye_scores), for channels without a clear one."""
    edges = sorted(b for b in blacks if any(a - 1 <= b <= z + 1 for a, z in quiet)) if quiet else sorted(blacks)
    if corners:
        found = best_logo([(c,) if isinstance(c, bytes) else c for c in corners])
        if found:
            if how is not None:
                how["by"] = "logo"
            return _logo_breaks(found[0], found[1], edges, sorted(blacks))
    if how is not None:
        how["by"] = "colour"  # which way it went, saved with the result: a later fix can redo just these
    breaks = _colour_breaks(hists, blacks, edges, quiet, program_end)
    if not eye:
        return breaks
    # A faint logo (the CBS eye) as well: a break found either way. On three CBS recordings the eye
    # alone never skipped any show and found what colour missed (Survivor 59% -> 96% of the ads),
    # while colour found the breaks full of CBS's own promos, which carry the eye (2026-10-30)
    if how is not None:
        how["by"] = "colour+eye"
    by_eye = _logo_breaks(eye, EYE_ON, edges, sorted(blacks), nearest_start=True)
    return _join((breaks or []) + by_eye) if breaks is not None or by_eye else breaks


def _colour_breaks(hists: List[List[float]], blacks: List[float], edges: List[float],
                   quiet: Optional[List[Tuple[float, float]]], program_end: Optional[float]) -> Optional[List[Dict[str, float]]]:
    """No clear logo: the seconds that don't look like the show, and the pieces between black-and-
    silent moments that look like ads on average. None if show and ads don't separate."""
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
        breaks = _join(breaks + _marked_pieces(scores, t, edges, n, program_end))
        breaks = _without_long_pieces(breaks, edges, n)
        breaks = _opening_to_edge(breaks, edges)
    return breaks


def _opening_to_edge(breaks: List[Dict[str, float]], edges: List[float]) -> List[Dict[str, float]]:
    """A break at the very start of the recording (the end of whatever aired before) that doesn't end
    at a black-and-silent moment ends at its last one instead: Survivor's ran on from 0:20 to a black
    frame at 0:54, skipping the show's first 31 s (2026-10-30). The other seven test recordings'
    openings end at such a moment already, or have none."""
    out = []
    for br in breaks:
        if br["start"] < 1 and not any(abs(e - br["end"]) <= 1 for e in edges):
            before = [e for e in edges if 10 <= e < br["end"]]
            if before:
                br = {"start": 0.0, "end": round(max(before), 1)}
        out.append(br)
    return out


def _without_long_pieces(breaks: List[Dict[str, float]], edges: List[float], n: int) -> List[Dict[str, float]]:
    """A break never holds a whole stretch of more than MAX_AD_PIECE_SECONDS between two black-and-
    silent moments: that stretch is show, and is cut out of it. Survivor's firelit Tribal Council
    (597 s between two of them) scored less like the show than the ads did, and colour alone took
    75:21-87:34 for one break, ten minutes of show (2026-10-30). Only a stretch wholly inside the
    break: Jeopardy's breaks start without such a moment, so the stretch before each one runs into it
    and is left alone."""
    cuts: List[float] = []
    for b in [0.0] + edges + [float(n)]:
        if not cuts or b - cuts[-1] > 5:
            cuts.append(b)
    long_pieces = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a > MAX_AD_PIECE_SECONDS]
    out = []
    for br in breaks:
        parts = [(br["start"], br["end"])]
        for a, b in long_pieces:
            kept = []
            for s, e in parts:
                if s - 1 <= a and b <= e + 1:
                    kept += [p for p in ((s, a), (b, e)) if p[1] - p[0] >= MIN_BREAK_SECONDS]
                else:
                    kept.append((s, e))
            parts = kept
        out += [{"start": round(s, 1), "end": round(e, 1)} for s, e in parts]
    return out


def _marked_pieces(scores: List[float], t: float, edges: List[float], n: int,
                   program_end: Optional[float] = None) -> List[Dict[str, float]]:
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
    # The show's last segment often runs straight into the closing break with no black-and-silent
    # moment between them (Jeopardy: Final Jeopardy and the station's ads were one piece, and the
    # piece looked like ads), so a piece across the scheduled end is never taken whole
    if program_end:
        ad = [x and not (a + 5 < program_end < b - 5) for (a, b), x in zip(spans, ad)]
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
# Read the recording as fast as the Tablo sends it and the PC keeps up (about 14x: a 30-minute show
# in 2 minutes, 2026-10-25). While another app watches live TV from the Tablo, 4x real time instead,
# so this doesn't compete with it. Anything TabloView plays or exports stops the analysis altogether.
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


def redo_episodes() -> List[str]:
    """Recordings done by the finder alone, asked to be done again with Claude (episode menu)."""
    return list(load_settings().get("commercial_redo") or [])


def queue_redo(*episode_ids: str) -> None:
    save_settings({"commercial_redo": [e for e in redo_episodes() if e not in episode_ids] + list(episode_ids)})


def _redo_done(episode_id: str) -> None:
    if episode_id in redo_episodes():
        save_settings({"commercial_redo": [e for e in redo_episodes() if e != episode_id]})


def pending(shows: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Finished recordings not analyzed yet: single ones asked for first, then the unwatched ones of
    the enabled shows, newest first."""
    shows = enabled_shows() if shows is None else shows
    queued = queued_episodes()
    redo = redo_episodes()
    if not shows and not queued and not redo:
        return []
    marks = ",".join("?" * len(shows)) or "''"
    qmarks = ",".join("?" * len(queued)) or "''"
    rmarks = ",".join("?" * len(redo)) or "''"
    # A Claude key added since a recording was done: once more, for Claude's breaks (one try each,
    # so a key that stops working doesn't read the same recordings over and over)
    settings = load_settings()
    claude_since = settings.get("claude_key_added") if settings.get("claude_api_key") else None
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT e.id, e.path, e.show_id, e.show_title, e.season_number, e.episode_number, e.duration, e.raw_json
            FROM episodes e
            LEFT JOIN commercials c ON c.episode_id = e.id
            WHERE (c.episode_id IS NULL
                   -- found by an older detector: again (it kept the old breaks meanwhile), unless watched
                   OR (COALESCE(c.method, 1) < {METHOD} AND c.status IN ('done', 'unreliable') AND e.status != 'Watched')
                   OR (? IS NOT NULL AND COALESCE(c.by_claude, 0) = 0 AND c.analyzed_at < ?
                       AND c.status IN ('done', 'unreliable') AND e.status != 'Watched'))
              AND (e.id IN ({qmarks}) OR (e.show_id IN ({marks}) AND e.status != 'Watched'))
               -- asked for again with Claude from the episode menu, watched or not
               OR e.id IN ({rmarks})
            ORDER BY e.air_date DESC
        """, [claude_since, claude_since, *queued, *shows, *redo]).fetchall()
    found = []
    for r in rows:
        details = recording_details(r["raw_json"])
        if details["recording_state"] == "finished":
            se = f" S{r['season_number']}E{r['episode_number']}" if r["season_number"] and r["episode_number"] else ""
            found.append({"id": r["id"], "path": r["path"], "show_id": r["show_id"], "show_title": r["show_title"],
                          "title": f"{r['show_title']}{se}", "duration": details["actual_duration"] or r["duration"] or 0,
                          # where the show is scheduled to end in the recording (it starts a little in)
                          "program_end": details["program_start"] + r["duration"] if r["duration"] else None})
    first = set(queued) | set(redo)
    return sorted(found, key=lambda ep: ep["id"] not in first)  # stable: keeps newest first within each


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
    reason = _busy_with()
    return {"state": "paused" if reason else "waiting", "reason": reason, "waiting": len(queue)}


def _cached_pending() -> List[Dict[str, str]]:
    """pending(), at most every 15 s (the status line asks every few seconds)."""
    if time.time() - float(_summary_cache["at"]) > 15:
        _summary_cache["value"] = pending() if (enabled_shows() or queued_episodes() or redo_episodes()) else []
        _summary_cache["at"] = time.time()
    return _summary_cache["value"] or []


def _busy() -> bool:
    """Something is playing or exporting: analysis waits (it would compete for the Tablo and the PC)."""
    return _busy_with() is not None


def _busy_with() -> Optional[str]:
    """What analysis waits for, for the status line: "playing", "exporting" or None."""
    from .transcode import transcode_manager
    if transcode_manager.sessions:
        return "playing"
    if any(not t.done() for t in transcode_manager.export_tasks.values()):
        return "exporting"
    return None


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
            f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level[lv];"
            # [big]: which pixels of each bigger corner are lighter than the 5x5 around them, 1 bit each
            f"[0:v]fps=1,scale={EYE_SCALE_W}:{EYE_SCALE_H},format=gray,split=2[e1][e2];[e2]boxblur=2:1[e3];"
            f"[e1][e3]blend=all_expr='if(gt(A\\,B+{EYE_LIGHTER})\\,255\\,0)',split=4" + "".join(f"[g{i}]" for i in range(4)) + ";"
            + "".join(f"[g{i}]crop={EYE_W}:{EYE_H}:{cx}:{cy}[h{i}];" for i, (cx, cy) in
                      enumerate([(0, 0), (EYE_SCALE_W - EYE_W, 0), (0, EYE_SCALE_H - EYE_H), (EYE_SCALE_W - EYE_W, EYE_SCALE_H - EYE_H)]))
            + "".join(f"[h{i}]" for i in range(4)) + "vstack=inputs=4,format=monob[big]")


def _split_frame(frame: bytes) -> Tuple[bytes, Tuple[bytes, ...]]:
    """(the THUMB_W x THUMB_H rgb24 thumbnail, the grey corners) from one FFmpeg frame."""
    row = OUT_W * 3
    thumb = b"".join(frame[y * row:y * row + THUMB_W * 3] for y in range(THUMB_H))
    corners = tuple(bytes(frame[(THUMB_H + k * CORNER_H + y) * row + x * 3] for y in range(CORNER_H) for x in range(CORNER_W))
                    for k in range(len(CORNERS)))
    return thumb, corners


def eye_path(log_path) -> Path:
    return Path(str(log_path) + ".eye")


def eye_scores(path) -> Optional[List[float]]:
    """From the pass's [big] file: per second, the share of the faint logo's pixels lit, in the
    corner where it's clearest; None if no corner has one. Deletes the file."""
    row = (EYE_W + 7) // 8
    per_corner = row * EYE_H
    per = per_corner * 4
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    finally:
        Path(path).unlink(missing_ok=True)
    n = len(data) // per
    if n < 120:
        return None

    def bits(sec: int, k: int) -> bytes:
        return data[sec * per + k * per_corner:sec * per + (k + 1) * per_corner]

    best = None
    for k in range(4):
        # How often each pixel is lit, from every EYE_SAMPLE-th second
        counts = [0] * (per_corner * 8)
        samples = range(0, n, EYE_SAMPLE)
        for sec in samples:
            for j, byte in enumerate(bits(sec, k)):
                if byte:
                    for b in range(8):
                        if byte & (0x80 >> b):
                            counts[j * 8 + b] += 1
        cut = EYE_PIXEL_SHARE * len(samples)
        # Not the outer EYE_EDGE pixels: FFmpeg's blur makes the picture's own edge (often a thin line)
        # look lighter than its surroundings in every second, ads included; no logo sits there
        logo = [(i // 8, 0x80 >> (i % 8)) for i, cnt in enumerate(counts) if cnt > cut
                and EYE_EDGE <= i % (row * 8) < EYE_W - EYE_EDGE and EYE_EDGE <= i // (row * 8) < EYE_H - EYE_EDGE]
        if len(logo) >= EYE_MIN_PIXELS and (best is None or len(logo) > len(best[1])):
            best = (k, logo)
    if best is None:
        return None
    k, logo = best
    return [sum(1 for j, mask in logo if bits(sec, k)[j] & mask) / len(logo) for sec in range(n)]


def _analyze(url: str, log_path, stop: threading.Event, progress: Optional[Dict[str, object]] = None,
             rate: Optional[float] = None) -> Optional[Tuple[List[List[float]], List[Tuple[bytes, ...]]]]:
    """One FFmpeg pass: black frames, silences and loudness to the log, and per second a colour
    histogram and the four corners to us, read at rate x real time (None: as fast as it comes).
    None if stopped."""
    cmd = [FFMPEG_PATH, "-hide_banner", "-nostats", *(["-readrate", str(rate)] if rate else []), "-i", url,
           "-filter_complex", analysis_graph(),
           "-map", "[bd]", "-f", "null", "-",
           "-map", "[sd]", "-f", "null", "-",
           "-map", "[lv]", "-f", "null", "-",
           "-map", "[big]", "-f", "rawvideo", "-y", str(eye_path(log_path)),
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


# What the one pass measured, kept per recording (the test recordings' format, tests/data/ads): finding
# the breaks again after a fix, or with Claude, takes a moment instead of reading the recording from
# the Tablo again. About 1-2 MB per hour; kept FEATURES_KEEP_DAYS after the last use
FEATURES_DIR = DATA_DIR / "ad_features"
FEATURES_KEEP_DAYS = 90
FEATURES_VERSION = 1  # bump when the pass measures differently (corner size...): older files are read again


def _features_path(episode_id: str):
    return FEATURES_DIR / ("".join(c for c in episode_id if c.isalnum() or c in "_-") + ".json.gz")


def save_features(episode_id: str, hists: List[List[float]], corners: List[Tuple[bytes, ...]], blacks: List[float],
                  quiet: List[Tuple[float, float]], loud: List[float], eye: Optional[List[float]] = None) -> None:
    import base64
    import gzip
    import json
    bits = bytearray()
    for frame in corners:
        for corner in frame:
            lit = lighter_pixels(corner)
            for b in range(0, len(lit), 8):
                bits.append(sum(1 << x for x, on in enumerate(lit[b:b + 8]) if on))
    data = {"version": FEATURES_VERSION, "seconds": len(hists),
            "hists": base64.b64encode(bytes(min(255, round(v * 255)) for h in hists for v in h)).decode(),
            "lit": base64.b64encode(bytes(bits)).decode(),
            "blacks": [round(x, 2) for x in blacks], "silences": [[round(a, 2), round(b, 2)] for a, b in quiet],
            "loudness": base64.b64encode(bytes(max(0, min(255, round(-v * 2))) for v in loud)).decode(),  # -dB x 2
            "eye": base64.b64encode(bytes(round(v * 255) for v in eye)).decode() if eye else None}
    try:
        FEATURES_DIR.mkdir(parents=True, exist_ok=True)
        with gzip.open(_features_path(episode_id), "wt", encoding="utf-8") as f:
            json.dump(data, f)
        cutoff = time.time() - FEATURES_KEEP_DAYS * 86400
        for p in FEATURES_DIR.glob("*.json.gz"):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
    except OSError as e:
        print(f"[Commercials] Couldn't keep what was measured: {e}")


def load_features(episode_id: str) -> Optional[Dict[str, object]]:
    """{hists, corners, blacks, quiet} as the pass gave them, or None if not kept (or measured differently)."""
    import base64
    import gzip
    import json
    path = _features_path(episode_id)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != FEATURES_VERSION:
            return None
        path.touch()  # in use: kept longer
    except (OSError, ValueError):
        return None
    n = data["seconds"]
    raw = base64.b64decode(data["hists"])
    hists = [[v / 255 for v in raw[i * BINS:(i + 1) * BINS]] for i in range(n)]
    bits = base64.b64decode(data["lit"])
    px = CORNER_W * CORNER_H
    per = (px + 7) // 8
    corners = [tuple([bool(bits[(i * len(CORNERS) + j) * per + p // 8] >> (p % 8) & 1) for p in range(px)]
                     for j in range(len(CORNERS))) for i in range(n)]
    return {"hists": hists, "corners": corners, "blacks": data["blacks"],
            "quiet": [tuple(s) for s in data["silences"]],
            "eye": [v / 255 for v in base64.b64decode(data["eye"])] if data.get("eye") else None}


async def analyze(ep: Dict[str, str]) -> Optional[str]:
    """Find the breaks in one recording and save them. Returns the status, or None if it was
    interrupted (something started playing) and should be tried again later."""
    from .tablo_client import tablo_manager
    from .export_pace import something_playing
    from . import claude_ads, previews
    feats = await asyncio.to_thread(load_features, ep["id"])
    want_previews = claude_ads.api_key() and not previews.times(ep["id"])
    if feats is None or want_previews:
        watch = await tablo_manager.get_airing_watch_url(ep["path"])
        if want_previews and watch.get("bif_url_hd"):
            await previews.fetch(ep["id"], watch["bif_url_hd"], True)  # the pictures Claude reads
    if feats is None:
        url = watch.get("playlist_url")
        if not url:
            raise RuntimeError("the Tablo didn't return a stream")
        log_path = TRANSCODE_DIR / f"ads_{ep['id']}.log"
        stop = threading.Event()
        rate = READ_RATE if await something_playing() else None
        job = asyncio.get_running_loop().run_in_executor(None, _analyze, url, log_path, stop, status, rate)
        while not job.done():
            await asyncio.sleep(2)
            if _busy():
                stop.set()
                await job
                eye_path(log_path).unlink(missing_ok=True)
                return None
        result = await job
        if result is None:
            eye_path(log_path).unlink(missing_ok=True)
            return None
        hists, corners = result
        try:
            log = log_path.read_text(encoding="utf-8", errors="replace")
        finally:
            log_path.unlink(missing_ok=True)
        eye = await asyncio.to_thread(eye_scores, eye_path(log_path))
        feats = {"hists": hists, "corners": corners, "blacks": black_frames(log), "quiet": silences(log), "eye": eye}
        await asyncio.to_thread(save_features, ep["id"], hists, corners, feats["blacks"], feats["quiet"], loudness(log), eye)
    hists, blacks = feats["hists"], feats["blacks"]
    how: Dict[str, str] = {}
    breaks = find_breaks(hists, blacks, feats["corners"], feats["quiet"], ep.get("program_end"), how, feats.get("eye"))
    # With the user's Anthropic key: Claude's reading of the previews, on these black frames
    by_claude = await asyncio.to_thread(claude_ads.find, ep, sorted(blacks), float(len(hists)))
    if by_claude is not None:
        breaks = by_claude
    save_commercials(ep["id"], "unreliable" if breaks is None else "done", breaks, method=METHOD,
                     by_claude=by_claude is not None, found_by="claude" if by_claude is not None else how.get("by"))
    print(f"[Commercials] {ep['show_title']} {ep['id']}: "
          f"{'show and ads could not be told apart' if breaks is None else f'{len(breaks)} breaks'}"
          f"{' (found by Claude)' if by_claude is not None else ''}")
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
                if await analyze(ep) is not None:  # not interrupted by playback
                    _redo_done(ep["id"])
            except Exception as e:
                _redo_done(ep["id"])
                print(f"[Commercials] Couldn't analyze {ep['show_title']} {ep['id']}: {e}")
                save_commercials(ep["id"], "failed", error=str(e)[:300])
            finally:
                status["current"] = None
                _summary_cache["at"] = 0.0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Commercials] {e}")
