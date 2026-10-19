import random
import unittest

from app import commercials as c


def frame(rgb, noise, rnd):
    """A tiny rgb24 frame of roughly one colour."""
    px = []
    for _ in range(c.THUMB_W * c.THUMB_H):
        px += [max(0, min(255, v + rnd.randint(-noise, noise))) for v in rgb]
    return bytes(px)


def recording(layout, seed=1):
    """layout: [(seconds, 'show' | 'ad')]. The show is always blue; each ad second is a random colour."""
    rnd = random.Random(seed)
    hists, blacks, t, prev = [], [], 0, None
    for secs, kind in layout:
        if prev is not None and prev != kind:
            blacks.append(t)  # black frames at the edges of breaks
        for _ in range(secs):
            rgb = (30, 60, 200) if kind == "show" else (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
            hists.append(c.histogram(frame(rgb, 20, rnd)))
        t += secs
        prev = kind
    return hists, blacks


class CommercialTests(unittest.TestCase):
    def test_finds_the_breaks_with_edges_at_the_black_frames(self):
        hists, blacks = recording([(300, "show"), (120, "ad"), (330, "show"), (150, "ad"), (400, "show")])
        self.assertEqual(c.find_breaks(hists, blacks), [{"start": 300.0, "end": 420.0}, {"start": 750.0, "end": 900.0}])

    def test_short_show_graphics_are_not_breaks(self):
        # A 25 s odd-looking stretch with no black frames (like Jeopardy's Final Jeopardy reveal)
        hists, _ = recording([(300, "show"), (25, "ad"), (300, "show")])
        self.assertEqual(c.find_breaks(hists, []), [])

    def test_no_guess_when_show_and_ads_look_alike(self):
        rnd = random.Random(3)
        hists = [c.histogram(frame((128, 128, 128), 5, rnd)) for _ in range(600)]
        self.assertIsNone(c.find_breaks(hists, [200.0, 300.0]))

    def test_black_frames_from_ffmpeg(self):
        log = "[blackdetect @ 0] black_start:312.7 black_end:312.8 black_duration:0.1\n"
        self.assertAlmostEqual(c.black_frames(log)[0], 312.75)


if __name__ == "__main__":
    unittest.main()
