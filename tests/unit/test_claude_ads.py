try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app import claude_ads, commercials
from app import database as db
from tests.unit.test_commercial_queue import episode


class EdgeTests(unittest.TestCase):
    def test_an_edge_moves_onto_the_black_frame_that_makes_the_break_shorter(self):
        # Shark Tank: two black frames near a start; the later one is where the show really stops
        found = claude_ads.onto_black_frames([[1745.0, 1966.0]], [1735.3, 1750.6, 1970.2, 1975.9], 3614)
        self.assertEqual(found, [{"start": 1750.6, "end": 1970.2}])

    def test_without_a_black_frame_nearby_an_edge_moves_into_the_break(self):
        # Better a few seconds of ad than any of the show
        self.assertEqual(claude_ads.onto_black_frames([[600.0, 800.0]], [], 3600), [{"start": 605.0, "end": 795.0}])

    def test_the_start_and_end_of_the_recording_stay_put(self):
        found = claude_ads.onto_black_frames([[0.0, 24.5], [3538.0, 3612.0]], [22.1, 3539.7], 3614)
        self.assertEqual(found, [{"start": 0.0, "end": 22.1}, {"start": 3539.7, "end": 3614.0}])

    def test_a_break_trimmed_to_nothing_is_dropped(self):
        self.assertEqual(claude_ads.onto_black_frames([[100.0, 112.0]], [], 3600), [])


class KeyTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM commercials")
            conn.commit()
        for ep in (episode("a1", "showa", air="2026-10-11T00:00Z"), episode("a2", "showa"),
                   episode("a3", "showa", status="Watched")):
            db.upsert_episode(ep)
        self.settings = {"commercial_shows": ["showa"], "commercial_episodes": []}
        p = mock.patch.object(commercials, "load_settings", side_effect=lambda: dict(self.settings))
        p.start()
        self.addCleanup(p.stop)

    def ids(self):
        return [e["id"] for e in commercials.pending()]

    def test_adding_a_key_redoes_unwatched_recordings_once(self):
        for ep_id in ("a1", "a2", "a3"):
            db.save_commercials(ep_id, "done", [], method=commercials.METHOD)
        self.assertEqual(self.ids(), [])
        self.settings.update(claude_api_key="sk-ant-test", claude_key_added="2999-01-01T00:00:00+00:00")
        self.assertEqual(self.ids(), ["a1", "a2"])  # not the watched one
        # Claude couldn't be asked (the finder's breaks were kept): not read again and again
        with mock.patch.object(db, "datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2999-01-02T00:00:00+00:00"
            db.save_commercials("a1", "done", [], method=commercials.METHOD)
        db.save_commercials("a2", "done", [], method=commercials.METHOD, by_claude=True)
        self.assertEqual(self.ids(), [])

    def test_no_key_nothing_is_redone(self):
        db.save_commercials("a1", "done", [], method=commercials.METHOD)
        self.settings.update(claude_api_key=None, claude_key_added="2999-01-01T00:00:00+00:00")
        self.assertEqual(self.ids(), ["a2"])  # a2 was never done at all

    def test_a_recording_asked_for_again_is_redone_once_even_if_watched(self):
        db.save_commercials("a3", "done", [], method=commercials.METHOD)
        self.settings["commercial_redo"] = ["a3"]
        with mock.patch.object(commercials, "save_settings", side_effect=lambda u: self.settings.update(u)):
            self.assertEqual(self.ids()[0], "a3")
            commercials._redo_done("a3")
        self.assertNotIn("a3", self.ids())

    def test_the_key_is_never_sent_to_the_page(self):
        from app.routes import system
        self.assertIn("claude_api_key", system.PRIVATE_SETTINGS)


if __name__ == "__main__":
    unittest.main()
