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
# /dev/marks): the share of ad time the finder must skip, and the most show it may skip. Raise
# these as the finder gets better; a change that makes any recording worse fails here.
FLOORS = {
    "hells_kitchen": (0.95, 60),   # Fox: corner logo
    "price_is_right": (0.72, 30),  # CBS: no logo, a set as colourful as the ads
    "boston_blue": (0.97, 20),     # CBS drama: no logo; breaks marked in /dev/marks
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
    """(share of ad seconds skipped, seconds of show skipped)."""
    ad = [any(a <= i < b for a, b in truth) for i in range(n)]
    skip = [any(b["start"] <= i < b["end"] for b in found or []) for i in range(n)]
    return sum(a and s for a, s in zip(ad, skip)) / max(1, sum(ad)), sum(s and not a for a, s in zip(ad, skip))


class RealRecordingTests(unittest.TestCase):
    def test_each_recording_keeps_its_accuracy(self):
        for name, (floor, show_limit) in FLOORS.items():
            with self.subTest(name):
                rec, hists, corners = load(name)
                found = c.find_breaks(hists, rec["blacks"], corners, [tuple(s) for s in rec["silences"]])
                share, show = score(found, rec["breaks"], rec["seconds"])
                print(f"\n  {name} ({rec['channel']}): {share:.0%} of ad time skipped, {show} s of show skipped")
                self.assertGreaterEqual(share, floor)
                self.assertLessEqual(show, show_limit)


if __name__ == "__main__":
    unittest.main()
