try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import base64
import gzip
import json
import unittest
from pathlib import Path

from app import commercials as c

DATA = Path(__file__).resolve().parent.parent / "data" / "ads"

# Real recordings, with where the breaks really are (checked frame by frame, or marked in
# /dev/marks): the share of ad time during the show the finder must skip, and the most show it may
# skip. Only the show itself counts, up to where its last scene ends (show_end, seconds): after
# that come credits, the station's closing break and the next show, which nobody watches for.
# Raise the floors as the finder gets better; a change that makes any recording worse fails.
FLOORS = {  # name: (share of ads skipped, most show skipped, show_end)
    "hells_kitchen": (0.97, 10, 3700),   # Fox: corner logo
    "price_is_right": (0.78, 20, 3470),  # CBS: no logo, a set as colourful as the ads
    "boston_blue": (0.97, 10, 3476),     # CBS drama: no logo
    "elsbeth": (0.97, 10, 3409),         # CBS drama: no logo
    "jeopardy": (0.97, 10, 1685),        # syndicated, no logo; Final Jeopardy runs into the closing break
    "tracker": (0.97, 10, 3453),         # CBS drama: the logo too faint to use; a dim drug ad opens a break
    # ABC: a see-through logo that drops out on bright scenes and comes back 18-37 s after the show
    # does (checked against the Tablo's 10-second previews; before the fix 248 s of show was skipped)
    "shark_tank": (0.97, 15, 3509),
    # CBS, no logo: the firelit Tribal Council scores less like the show than the ads do, so colour alone
    # took ten minutes of it for a break (627 s of show) until a break could no longer hold a whole long
    # stretch between black-and-silent moments; two real breaks are still missed. With an Anthropic key,
    # Claude finds them all (ClaudeAnswerTests)
    "survivor": (0.55, 35, 5250),
}

# Claude's answers from the preview sheets (app/claude_ads.py, prompt as shipped), 2026-10-30, one run
# each: they go through the same edge rule as in the app, so a change to it is checked against them
CLAUDE = {
    "survivor": [[0, 24.5], [875.5, 1045.5], [1465.5, 1626.5], [1967, 2277], [2817.5, 3137], [3798, 3968.5], [4369, 4649], [5250, 5470]],
    "hells_kitchen": [[0, 35], [815.5, 1026], [1456, 1706.5], [2056.5, 2297], [2677, 2937], [3237.5, 3428], [3738, 3788]],
    "price_is_right": [[0, 25], [625, 775], [1065, 1255], [1375, 1525], [1725, 1835], [2055, 2205], [2565, 2715], [2835, 3005], [3235, 3405], [3495, 3680]],
    "boston_blue": [[0, 24], [585, 755.5], [1175.5, 1345.5], [1947, 2247], [2777, 3047.5], [3478, 3683]],
    "elsbeth": [[0, 5], [775.5, 895], [1596, 1736], [2297, 2557], [2807, 3097.5], [3408, 3518], [3548, 3603]],
    "jeopardy": [[0, 14], [304.5, 424.5], [726, 895], [1355.5, 1576.5], [1686.5, 1876]],
    "tracker": [[0, 25], [975, 1125], [1575, 1735], [2105, 2405], [2855, 3145], [3455, 3595], [3625, 3680]],
    "shark_tank": [[0, 25], [625, 805], [1216, 1416], [1736, 1966], [2447, 2667], [3137.5, 3348], [3538, 3613]],
}


def load(name):
    with gzip.open(DATA / f"{name}.json.gz", "rt", encoding="utf-8") as f:
        rec = json.load(f)
    n = rec["seconds"]
    raw = base64.b64decode(rec["hists"])
    hists = [[v / 255 for v in raw[i * c.BINS:(i + 1) * c.BINS]] for i in range(n)]
    bits = base64.b64decode(rec["lit"])
    px = c.CORNER_W * c.CORNER_H
    per = (px + 7) // 8
    corners = []
    for i in range(n):
        corners.append(tuple(
            [bool(bits[((i * len(c.CORNERS) + j) * per) + p // 8] >> (p % 8) & 1) for p in range(px)]
            for j in range(len(c.CORNERS))))
    return rec, hists, corners


def score(found, truth, n):
    """(share of ad seconds skipped, seconds of show skipped), in the first n seconds."""
    ad = [any(a <= i < b for a, b in truth) for i in range(n)]
    skip = [any(b["start"] <= i < b["end"] for b in found or []) for i in range(n)]
    return sum(a and s for a, s in zip(ad, skip)) / max(1, sum(ad)), sum(s and not a for a, s in zip(ad, skip))


class RealRecordingTests(unittest.TestCase):
    def test_each_recording_keeps_its_accuracy(self):
        for name, (floor, show_limit, show_end) in FLOORS.items():
            with self.subTest(name):
                rec, hists, corners = load(name)
                found = c.find_breaks(hists, rec["blacks"], corners, [tuple(s) for s in rec["silences"]], rec["program_end"])
                share, show = score(found, rec["breaks"], show_end)
                print(f"\n  {name} ({rec['channel']}): {share:.0%} of ad time skipped, {show} s of show skipped")
                self.assertGreaterEqual(share, floor)
                self.assertLessEqual(show, show_limit)


class ClaudeAnswerTests(unittest.TestCase):
    def test_claude_answers_on_black_frames(self):
        from app import claude_ads
        total = 0
        for name, answer in CLAUDE.items():
            with self.subTest(name):
                rec, _, _ = load(name)
                found = claude_ads.onto_black_frames(answer, sorted(rec["blacks"]), rec["seconds"])
                share, show = score(found, rec["breaks"], FLOORS[name][2])
                print(f"\n  {name} with Claude: {share:.0%} of ad time skipped, {show} s of show skipped")
                self.assertGreaterEqual(share, 0.92)
                self.assertLessEqual(show, 20)
                total += show
        self.assertLessEqual(total, 30)  # 25 s across all eight when checked; the finder alone, 654 s


if __name__ == "__main__":
    unittest.main()
