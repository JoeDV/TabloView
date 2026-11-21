try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest

from app import database as db


def episode(ep_id, show_id, state):
    db.upsert_episode({"id": ep_id, "path": f"/recordings/series/episodes/{ep_id}", "show_id": show_id,
                       "show_title": show_id, "raw_json": {"video_details": {"state": state}}})


class RecordingNowTests(unittest.TestCase):
    """The Library's cards say Recording now while a show's newest recording is still in progress
    (a forum request: the card appears as the recording starts, with nothing to say it isn't done)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM shows")
            conn.execute("DELETE FROM episodes")
            conn.commit()
        for show in ("news", "drama"):
            db.upsert_show({"id": show, "title": show, "episode_count": 2})
        episode("n1", "news", "finished")
        episode("n2", "news", "recording")
        episode("d1", "drama", "finished")

    def test_only_the_show_being_recorded(self):
        flags = {s["id"]: s["recording_now"] for s in db.get_shows()}
        self.assertEqual(flags, {"news": True, "drama": False})

    def test_gone_once_it_finishes(self):
        episode("n2", "news", "finished")
        self.assertFalse(next(s for s in db.get_shows() if s["id"] == "news")["recording_now"])


if __name__ == "__main__":
    unittest.main()
