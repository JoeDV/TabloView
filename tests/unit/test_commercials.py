import random
import unittest
from unittest import mock

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


class EyeTests(unittest.TestCase):
    """The faint-logo check (CBS's eye) on the 1-bit corner masks FFmpeg writes."""

    def mask_file(self, seconds, lit):
        """seconds of four EYE_W x EYE_H corners; lit(sec, corner, x, y) -> bool."""
        import tempfile
        row = (c.EYE_W + 7) // 8
        out = bytearray()
        for sec in range(seconds):
            for k in range(4):
                for y in range(c.EYE_H):
                    bits = bytearray(row)
                    for x in range(c.EYE_W):
                        if lit(sec, k, x, y):
                            bits[x // 8] |= 0x80 >> (x % 8)
                    out += bits
        f = tempfile.NamedTemporaryFile(suffix=".eye", delete=False)
        f.write(bytes(out))
        f.close()
        return f.name

    def test_the_eye_is_found_and_the_frame_edge_ignored(self):
        ring = {(x, y) for x in range(20, 30) for y in range(40, 50) if x in (20, 29) or y in (40, 49)}
        ads = range(200, 260)
        # bottom-left corner: the ring, off during the ads; the picture's left edge lit all the time
        path = self.mask_file(400, lambda sec, k, x, y: k == 2 and (x == 0 or ((x, y) in ring and sec not in ads)))
        eye = c.eye_scores(path)
        self.assertIsNotNone(eye)
        self.assertEqual([round(v) for v in eye[195:205]], [1] * 5 + [0] * 5)

    def test_no_corner_with_a_logo(self):
        self.assertIsNone(c.eye_scores(self.mask_file(300, lambda sec, k, x, y: x == 0)))


class RatingTests(unittest.TestCase):
    """The show's own TV rating, learned in the opening, and breaks never running over it."""

    @staticmethod
    def box(x0, y0, w, h, letters):
        """Lit pixels of a rating box: its outline, and what's written in it (a set of (x, y) inside)."""
        lit = {(x, y) for x in range(x0, x0 + w + 1) for y in range(y0, y0 + h + 1)
               if x in (x0, x0 + w) or y in (y0, y0 + h)}
        return lit | {(x0 + x, y0 + y) for x, y in letters}

    def rating_file(self, seconds, lit):
        """seconds of the monob top-left third; lit(sec) -> set of (x, y)."""
        import tempfile
        row = (c.RATING_W + 7) // 8
        out = bytearray()
        for sec in range(seconds):
            on = lit(sec)
            for y in range(c.RATING_H):
                bits = bytearray(row)
                for x in range(c.RATING_W):
                    if (x, y) in on:
                        bits[x // 8] |= 0x80 >> (x % 8)
                out += bits
        f = tempfile.NamedTemporaryFile(suffix=".rating", delete=False)
        f.write(bytes(out))
        f.close()
        return f.name

    # "TV 14 V" and a promo's "TV PG": different strokes
    SHOW = {(x, 10) for x in range(6, 22)} | {(14, y) for y in range(12, 36)}
    PROMO = {(x, 8) for x in range(5, 15)} | {(6, y) for y in range(8, 22)} | {(x, 22) for x in range(5, 15)}

    @staticmethod
    def noise(sec):
        """A busy picture behind: different pixels every second."""
        rnd = random.Random(sec)
        return {(rnd.randrange(160), rnd.randrange(90)) for _ in range(300)}

    def test_the_shows_own_rating_and_not_a_promos(self):
        show = self.box(23, 13, 35, 41, self.SHOW)
        promo = self.box(24, 14, 29, 30, self.PROMO)  # smaller, and other letters

        def lit(sec):
            if sec in range(20, 34) or sec in range(300, 304) or sec in range(600, 603):
                return show | self.noise(sec)
            if sec in range(200, 204) or sec in range(400, 404):
                return promo | self.noise(sec)
            if sec == 500:
                return show  # a single second isn't a showing
            return self.noise(sec)
        self.assertEqual(c.rating_boxes(self.rating_file(700, lit)), [(20, 34), (300, 304), (600, 603)])

    def test_lettering_without_a_box(self):
        # NBC writes the rating without a box around it
        letters = ({(40 + x, 20 + y) for x, y in self.SHOW} | {(40 + x, 50) for x in range(4, 24)}
                   | {(44, 20 + y) for y in range(26, 40)})
        on = set(range(30, 44)) | set(range(628, 640))
        self.assertEqual(c.rating_boxes(self.rating_file(700, lambda sec: letters if sec in on else set())),
                         [(30, 44), (628, 640)])

    def test_nothing_without_it_at_the_start_or_seen_only_there(self):
        show = self.box(23, 13, 35, 41, self.SHOW)
        # the recording missed the show's start
        self.assertEqual(c.rating_boxes(self.rating_file(400, lambda sec: show if 300 <= sec < 310 else set())), [])
        # a still graphic in the opening, never seen again
        self.assertEqual(c.rating_boxes(self.rating_file(400, lambda sec: show if 10 <= sec < 30 else set())), [])

    def test_breaks_never_run_over_the_shows_rating(self):
        breaks = [{"start": 100.0, "end": 300.0}, {"start": 500.0, "end": 700.0}, {"start": 900.0, "end": 960.0},
                  {"start": 1100.0, "end": 1196.0}, {"start": 1400.0, "end": 1500.0}]
        rating = [(282, 286), (498, 503), (930, 934), (1223, 1238), (1600, 1610)]
        blacks = [150.0, 270.0, 520.0, 1196.0, 1209.0, 1222.0]
        edges = [1196.0, 1222.0]
        found = c._not_over_rating(breaks, rating, blacks, edges)
        self.assertEqual(found, [
            {"start": 100.0, "end": 270.0},    # back at the last black frame before the rating
            {"start": 503.0, "end": 700.0},    # starting while it shows: after it
            # 900-960: too short once cut
            {"start": 1100.0, "end": 1222.0},  # a promo after the logo came back: to the rating's edge
            {"start": 1400.0, "end": 1500.0},  # the rating 100 s later: nothing to do with it
        ])
        self.assertEqual(c._not_over_rating(breaks, [], []), breaks)
        self.assertIsNone(c._not_over_rating(None, rating, []))


class AskedDoneTests(unittest.TestCase):
    """Find again from saved measurements takes seconds: the status line says it happened (the user,
    2026-10-31: "nothing started and the Tablo isn't being used")."""

    def setUp(self):
        from app import commercials as C
        self.C = C
        C._asked_done.update(count=0, at=0.0, title=None)
        C.status["current"] = None

    def summary(self, now):
        with mock.patch.object(self.C, "_cached_pending", return_value=[]), \
                mock.patch.object(self.C.time, "time", return_value=now):
            return self.C.summary()

    def test_shown_for_a_while_then_gone(self):
        with mock.patch.object(self.C.time, "time", return_value=1000.0):
            self.C._note_asked_done("Survivor S49E7")
            self.C._note_asked_done("Survivor S49E8")
        self.assertEqual(self.summary(1050.0), {"state": "finished", "count": 2, "title": "Survivor S49E8", "waiting": 0})
        self.assertIsNone(self.summary(1000.0 + self.C.DONE_SHOWN_SECONDS + 1))

    def test_a_later_one_starts_a_new_count(self):
        with mock.patch.object(self.C.time, "time", return_value=1000.0):
            self.C._note_asked_done("A")
        with mock.patch.object(self.C.time, "time", return_value=5000.0):
            self.C._note_asked_done("B")
        self.assertEqual(self.summary(5010.0)["count"], 1)
