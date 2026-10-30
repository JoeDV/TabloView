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


if __name__ == "__main__":
    unittest.main()
