try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone

from app import recommend


def show(path, title, genres, new=1, premiere=None):
    return {"path": path, "title": title, "genres": genres, "new_episodes": new, "premiere": premiere}


class ByGenreTests(unittest.TestCase):
    def setUp(self):
        self.liked = [show("/l/1", "Scrubs", ["Sitcom", "Medical"]), show("/l/2", "Jeopardy!", ["Game Show"])]
        self.every = [["sitcom"], ["sitcom"], ["drama"], ["drama"], ["drama"], ["game show"], ["medical"], ["cooking"]]

    def test_closest_first_with_the_recorded_shows_its_like(self):
        found = recommend.by_genre(self.liked, [
            show("/c/1", "Cooking Show", ["Cooking"]),
            show("/c/2", "Medical Sitcom", ["Sitcom", "Medical"]),
            show("/c/3", "Quiz", ["Game Show"]),
        ], self.every)
        self.assertEqual([s["title"] for s in found], ["Medical Sitcom", "Quiz"])  # nothing like Cooking Show
        self.assertEqual(found[0]["because"], ["Scrubs"])

    def test_reruns_count_for_less(self):
        found = recommend.by_genre(self.liked, [
            show("/c/1", "Old Sitcom", ["Sitcom", "Medical"], new=0),
            show("/c/2", "New Sitcom", ["Sitcom", "Medical"], new=3),
        ], self.every)
        self.assertEqual([s["title"] for s in found], ["New Sitcom", "Old Sitcom"])

    def test_a_premiere_further_down_still_makes_it_and_goes_first(self):
        candidates = [show(f"/c/{i}", f"Quiz {i:02d}", ["Game Show"]) for i in range(recommend.PICKS + 3)]
        candidates.append(show("/c/p", "New Comedy", ["Sitcom"], premiere={"kind": "series", "datetime": "2026-11-20T01:00Z"}))
        found = recommend.by_genre(self.liked, candidates, self.every)
        self.assertEqual(found[0]["title"], "New Comedy")
        self.assertEqual(len(found), recommend.PICKS + 1)


class PremiereOrderTests(unittest.TestCase):
    def test_series_then_season_soonest_first_then_the_rest_in_order(self):
        found = recommend.premieres_first([
            show("/a", "A", []),
            show("/b", "B", [], premiere={"kind": "season", "datetime": "2026-11-19T01:00Z"}),
            show("/c", "C", [], premiere={"kind": "special", "datetime": "2026-11-18T01:00Z"}),
            show("/d", "D", [], premiere={"kind": "series", "datetime": "2026-11-25T01:00Z"}),
            show("/e", "E", [], premiere={"kind": "season", "datetime": "2026-11-18T01:00Z"}),
        ])
        self.assertEqual([s["title"] for s in found], ["D", "E", "B", "A", "C"])


class ClaudeAnswerTests(unittest.TestCase):
    def test_only_listed_shows_once_each_with_a_real_reason(self):
        candidates = [show("/c/1", "Family Feud", []), show("/c/2", "Matlock", []), show("/c/3", "Chicago Fire", [])]
        picks = recommend.matched([
            {"title": "family feud", "why": "A classic game show like The Price Is Right."},
            {"title": "Not In The Guide", "why": "A show that isn't airing on these channels."},
            {"title": "Family Feud", "why": "The same show again, picked twice by mistake."},
            {"title": "Matlock", "why": "placeholder"},
            {"title": "Chicago Fire", "why": "Fire"},
        ], candidates)
        self.assertEqual(picks, [{"path": "/c/1", "why": "A classic game show like The Price Is Right."}])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)
        self.cached = {"liked": ["/l/1", "/l/2"], "at": (self.now - timedelta(days=2)).isoformat(),
                       "picks": [{"path": f"/c/{i}", "why": "x" * 20} for i in range(8)]}
        self.airing = {f"/c/{i}" for i in range(8)}

    def test_kept_while_nothing_changed(self):
        self.assertTrue(recommend.still_good(self.cached, ["/l/1", "/l/2"], self.airing, self.now))

    def test_asked_again_when_the_recorded_series_change(self):
        self.assertFalse(recommend.still_good(self.cached, ["/l/1", "/l/2", "/l/3"], self.airing, self.now))

    def test_asked_again_after_a_week(self):
        self.assertFalse(recommend.still_good(self.cached, ["/l/1", "/l/2"], self.airing, self.now + timedelta(days=6)))

    def test_asked_again_when_few_are_still_airing_unrecorded(self):
        self.assertFalse(recommend.still_good(self.cached, ["/l/1", "/l/2"], {"/c/0", "/c/1", "/c/2"}, self.now))

    def test_asked_when_there_are_none(self):
        self.assertFalse(recommend.still_good(None, ["/l/1"], self.airing, self.now))


if __name__ == "__main__":
    unittest.main()
