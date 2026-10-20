"""Live picture quality ("signal") meter for antenna channels.

The Tablo doesn't report signal strength, but the damage a weak signal does is visible in FFmpeg's
log as live TV is converted:
- a frame whose packets were flagged as broken is thrown away (-fflags +discardcorrupt) and logged as
  "Packet corrupt (stream = <video>, ...), dropping it". Tested on a clean 1080i recording with broken
  and missing packets added: the count matches the frames lost almost exactly (87 of 87, 461 of 461,
  448 of 454).
- a frame that arrives damaged without the flag (what real WTHR breakup looked like) is patched over
  by the decoder ("concealing N DC, N AC, N MV errors") and logged as "corrupt decoded frame".
- frames that never arrive leave a jump in the video's timeline: FFmpeg's progress line moves on
  further in time than the frames it made would cover (with Smooth motion, FFmpeg fills the gap with
  copies and counts them as "dup").
Each counts as a frame that didn't arrive intact.

A pause in FFmpeg's progress isn't damage in itself: live TV comes from the Tablo in chunks of a few
seconds, and a late chunk just means FFmpeg waits and then races through it (WTHR, 2026-10-20: every
2 s pause was followed by exactly the frames due, 199 frames for 6.64 s of timeline). So a pause is
scored once frames come again, by whether the timeline jumped.

Score each second = share of the frames due that arrived intact. Read from the session's ffmpeg.log;
nothing extra is asked of the Tablo.
"""

import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

HISTORY_SECONDS = 300  # the graph: last 5 minutes
NO_SIGNAL_SECONDS = 5.0  # nothing for this long: the badge says No signal (about when the player would freeze)
# Frames missing from the timeline are counted from a running total (timeline x output fps - frames
# made + copies filled in): second by second it wobbles by a few frames as the encoder holds some
# back, but over a session it stays put (WTHR, 2 minutes: within -4.3..+3.7 frames). A step beyond
# this many frames is frames lost.
MISSING_STEP_FRAMES = 10
WARMUP_SECONDS = 15.0  # FFmpeg copies frames at the start while lining video up with sound (115 on WTHR, until 11 s)
BADGE_SECONDS = 3  # the badge shows the average of the last few seconds, so it doesn't flicker

_VIDEO = re.compile(r"Stream #0:(\d+)\S*: Video: .*?([\d.]+) fps")
_OUT_VIDEO = re.compile(r"Output #0.*?Stream #0:\d+\S*: Video: .*?([\d.]+) fps", re.S)
_PROGRESS = re.compile(r"frame=\s*(\d+).*?time=(-?)(\d+):(\d+):([\d.]+)(?:.*?dup=(\d+))?")


def state_for(score: Optional[float]) -> str:
    if score is None:
        return "starting"
    if score >= 99:
        return "clean"
    if score >= 90:
        return "minor"
    if score >= 50:
        return "breaking"
    if score > 0:
        return "losing"
    return "no_signal"


class Meter:
    """Follows one live session's ffmpeg.log. Call sample() about once a second."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.offset = 0
        self.partial = ""
        self.header = ""
        self.fps: Optional[float] = None  # the broadcast's frames per second
        self.out_fps: Optional[float] = None  # FFmpeg's output (twice the broadcast's with Smooth motion)
        self.corrupt_pattern: Optional[re.Pattern] = None
        self.last: Optional[Tuple[int, float, int]] = None  # last progress: frames, timeline seconds, dup
        self.missing_ref: Optional[float] = None  # the running total's settled level (see MISSING_STEP_FRAMES)
        self.last_progress: Optional[float] = None
        self.quiet: List[float] = []  # seconds sampled with no progress, scored when frames come again
        self.corrupt_waiting = 0  # damaged frames logged while quiet
        self.history: Deque[Tuple[float, float]] = deque(maxlen=HISTORY_SECONDS)

    def _read_new(self) -> str:
        try:
            with open(self.log_path, "rb") as f:
                f.seek(self.offset)
                data = f.read()
        except OSError:
            return ""
        self.offset += len(data)
        text = self.partial + data.decode("utf-8", errors="replace")
        # Keep an unfinished last line (FFmpeg ends progress lines with \r) for next time
        cut = max(text.rfind("\n"), text.rfind("\r"))
        self.partial = text[cut + 1:]
        return text[:cut + 1]

    def _streams(self, text: str) -> None:
        """The broadcast's and the output's frame rates, from FFmpeg's description of the streams."""
        self.header = (self.header + text)[:20000]
        m = _VIDEO.search(self.header)
        out = _OUT_VIDEO.search(self.header)
        if m and out:
            video_stream, self.fps, self.out_fps = m.group(1), float(m.group(2)), float(out.group(1))
            self.corrupt_pattern = re.compile(
                rf"Packet corrupt \(stream = {video_stream},"
                rf"|\[vist#0:{video_stream}/[^\]]*\] \[dec:[^\]]*\] corrupt decoded frame")

    def _add(self, stamps: List[float], score: float) -> None:
        if stamps and self.history and stamps[0] < self.history[-1][0]:
            self.history = deque(sorted(list(self.history) + [(t, score) for t in stamps]), maxlen=HISTORY_SECONDS)
        else:
            self.history.extend((t, score) for t in stamps)

    def sample(self, now: Optional[float] = None) -> Optional[float]:
        """Read what FFmpeg logged since the last call and score it (None while tuning, or during a
        pause, which is scored when frames come again)."""
        now = time.time() if now is None else now
        text = self._read_new()
        if self.corrupt_pattern is None:
            self._streams(text)
            if self.corrupt_pattern is None:
                return None
        corrupt = len(self.corrupt_pattern.findall(text)) + self.corrupt_waiting
        prog = _PROGRESS.findall(text)
        if not prog:
            if self.last_progress is None:
                return None  # converting hasn't started yet
            self.quiet.append(now)
            self.corrupt_waiting = corrupt
            return None
        frames_s, neg, h, m, s, dup_s = prog[-1]
        cur = (int(frames_s), 0.0 if neg else int(h) * 3600 + int(m) * 60 + float(s), int(dup_s or 0))
        if self.last is None or cur[0] < self.last[0]:
            # The first progress, or a restarted FFmpeg (it counts from 0 again): a new starting point
            self.last, self.last_progress = cur, now
            self.quiet, self.corrupt_waiting, self.missing_ref = [], 0, None
            return None
        new_frames = cur[0] - self.last[0]
        if new_frames == 0:
            self.quiet.append(now)
            self.corrupt_waiting = corrupt
            return None
        timeline = max(cur[1] - self.last[1], 0.0)
        copying = cur[2] > self.last[2]
        self.last, self.last_progress = cur, now
        # Frames the timeline moved past without FFmpeg making them, plus the copies it filled in with
        missing_out = 0.0
        if cur[1] >= WARMUP_SECONDS:
            total = cur[1] * self.out_fps - cur[0] + cur[2]
            if self.missing_ref is None:
                if not copying:
                    self.missing_ref = total  # start counting once the start-up copies are done
            elif total - self.missing_ref > MISSING_STEP_FRAMES:
                missing_out, self.missing_ref = total - self.missing_ref, total
            elif total < self.missing_ref - MISSING_STEP_FRAMES:
                self.missing_ref = total
        missing = missing_out * self.fps / self.out_fps  # in the broadcast's frames
        due = max(timeline * self.fps, 1.0)
        score = round(100 * max(0.0, 1 - (corrupt + missing) / due), 1)
        self._add(self.quiet + [now], score)
        self.quiet, self.corrupt_waiting = [], 0
        return score

    def report(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        hist = list(self.history)
        no_signal = self.last_progress is not None and bool(self.quiet) and now - self.last_progress >= NO_SIGNAL_SECONDS
        if no_signal:
            hist = hist + [(t, 0.0) for t in self.quiet]  # shown as lost while it lasts
        if not hist:
            return {"state": "starting", "score": None, "history": [], "worst": None, "dropouts": 0}
        if no_signal:
            badge = 0.0
        else:
            recent = [s for t, s in hist if now - t <= BADGE_SECONDS + 0.5] or [hist[-1][1]]
            badge = round(sum(recent) / len(recent))
        worst_t, worst = min(hist, key=lambda h: h[1])
        # Dropouts: times the picture went from watchable to breaking up badly or lost
        dropouts = sum(1 for (_, a), (_, b) in zip(hist, hist[1:]) if a >= 50 > b)
        return {
            "state": state_for(badge),
            "score": badge,
            "history": [[round(t - now, 1), s] for t, s in hist],
            "worst": {"score": worst, "seconds_ago": round(now - worst_t)} if worst < 99 else None,
            "dropouts": dropouts,
        }
