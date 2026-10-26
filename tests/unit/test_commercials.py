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

    def test_silences_from_ffmpeg(self):
        log = ("[silencedetect @ 0] silence_start: 824.1\n"
               "[silencedetect @ 0] silence_end: 824.6 | silence_duration: 0.5\n")
        self.assertEqual(c.silences(log), [(824.1, 824.6)])


LOGO = {(y, x) for y in range(14, 19) for x in range(14, 30) if (x + y) % 3}  # a few rows of light "text"


def corner(logo_on, rnd):
    """A grey corner: a changing picture, with the channel's logo lighter on top of it or not."""
    px = bytearray(rnd.randint(40, 120) for _ in range(c.CORNER_W * c.CORNER_H))
    if logo_on:
        for y, x in LOGO:
            px[y * c.CORNER_W + x] = min(255, px[y * c.CORNER_W + x] + 90)
    return bytes(px)


def logo_recording(layout, seed=2):
    """layout: [(seconds, 'show' | 'ad' | 'promo')]. The show and Fox-style promos carry the logo, ads
    don't; the show is also the same colour as the ads, so colour alone can't tell them apart. Each
    ad-to-show change has a black, silent frame. The logo comes back LOGO_RETURN_LAG after the show."""
    rnd = random.Random(seed)
    hists, corners, blacks, quiet, t, prev = [], [], [], [], 0, None
    for secs, kind in layout:
        if prev is not None and (prev == "show") != (kind == "show"):
            blacks.append(float(t))
            quiet.append((t - 0.3, t + 0.3))
        for i in range(secs):
            hists.append(c.histogram(frame((rnd.randint(0, 255),) * 3, 20, rnd)))
            on = kind == "promo" or (kind == "show" and (prev in (None, "show") or i >= c.LOGO_RETURN_LAG))
            corners.append(corner(on, rnd))
        t += secs
        prev = kind
    return hists, corners, blacks, quiet


class LogoTests(unittest.TestCase):
    """US networks take their corner logo off for the ads: on Hell's Kitchen this found all five
    breaks, where colour found 47 s of two."""

    def test_breaks_are_where_the_logo_is_gone(self):
        hists, corners, blacks, quiet = logo_recording([(300, "show"), (180, "ad"), (400, "show"), (240, "ad"), (300, "show")])
        self.assertEqual(c.find_breaks(hists, blacks, corners, quiet),
                         [{"start": 300.0, "end": 480.0}, {"start": 880.0, "end": 1120.0}])

    def test_a_promo_with_the_logo_inside_a_break_doesnt_split_it(self):
        hists, corners, blacks, quiet = logo_recording([(300, "show"), (90, "ad"), (20, "promo"), (90, "ad"), (400, "show")])
        breaks = c.find_breaks(hists, blacks, corners, quiet)
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["start"], 300.0)

    def test_no_logo_pieces_between_quiet_black_frames(self):
        # Price Is Right: no logo, and a third of the ad seconds look like the colourful set, which
        # splits colour runs; the pieces between black-and-silent moments still average like ads
        rnd = random.Random(9)
        layout = [(300, "show"), (70, "ad"), (60, "ad"), (330, "show")]
        hists, blacks, quiet, t = [], [], [], 0
        for secs, kind in layout:
            if t:
                blacks.append(float(t))
                quiet.append((t - 0.3, t + 0.3))
            for i in range(secs):
                blue = kind == "show" or i % 3 == 0
                rgb = (30, 60, 200) if blue else (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
                hists.append(c.histogram(frame(rgb, 20, rnd)))
            t += secs
        corners = [corner(False, rnd) for _ in hists]
        self.assertEqual(c.find_breaks(hists, blacks, corners, quiet), [{"start": 300.0, "end": 430.0}])

    def test_an_ad_that_looks_like_the_show_next_to_a_break_is_part_of_it(self):
        # Tracker, CBS (2026-10-25): the break opened with a dim one-minute drug ad (62 s between two
        # black-and-silent moments) that scored like the show, so the first minute of ads played
        rnd = random.Random(11)
        layout = [(400, "show"), (62, "show-like ad"), (90, "ad"), (400, "show")]
        hists, blacks, quiet, t = [], [], [], 0
        for secs, kind in layout:
            if t:
                blacks.append(float(t))
                quiet.append((t - 0.3, t + 0.3))
            for _ in range(secs):
                rgb = (30, 60, 200) if kind != "ad" else (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
                hists.append(c.histogram(frame(rgb, 20, rnd)))
            t += secs
        corners = [corner(False, rnd) for _ in hists]
        self.assertEqual(c.find_breaks(hists, blacks, corners, quiet), [{"start": 400.0, "end": 552.0}])

    def test_no_logo_falls_back_to_colour(self):
        hists, blacks = recording([(300, "show"), (120, "ad"), (330, "show"), (150, "ad"), (400, "show")])
        rnd = random.Random(5)
        corners = [corner(False, rnd) for _ in hists]
        self.assertEqual(c.find_breaks(hists, blacks, corners, []), [{"start": 300.0, "end": 420.0}, {"start": 750.0, "end": 900.0}])


if __name__ == "__main__":
    unittest.main()
