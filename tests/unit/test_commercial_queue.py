import unittest
from unittest import mock

from app import commercials
from app import database as db


def episode(id, show, status="Unwatched", state="finished", air="2026-10-10T00:00Z"):
    return {"id": id, "show_id": show, "show_title": show, "path": f"/recordings/series/episodes/{id}", "season_number": 1,
            "episode_number": 1, "title": id, "air_date": air, "duration": 1800, "status": status,
            "raw_json": {"video_details": {"state": state}}}


class CommercialQueueTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM commercials")
            conn.commit()
        for ep in (episode("a1", "showa", air="2026-10-11T00:00Z"), episode("a2", "showa"),
                   episode("a3", "showa", status="Watched"), episode("b1", "showb", status="Watched"),
                   episode("b2", "showb", state="recording")):
            db.upsert_episode(ep)
        self.settings = {"commercial_shows": [], "commercial_episodes": []}
        for p in (mock.patch.object(commercials, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(commercials, "save_settings", side_effect=lambda u: self.settings.update(u))):
            p.start()
            self.addCleanup(p.stop)

    def ids(self):
        return [e["id"] for e in commercials.pending()]

    def test_a_show_does_its_unwatched_finished_recordings_newest_first(self):
        self.settings["commercial_shows"] = ["showa"]
        self.assertEqual(self.ids(), ["a1", "a2"])

    def test_a_single_recording_goes_first_even_if_watched_or_its_show_is_off(self):
        self.settings["commercial_shows"] = ["showa"]
        commercials.queue_episode("b1")
        self.assertEqual(self.ids(), ["b1", "a1", "a2"])

    def test_done_or_still_recording_is_left_out(self):
        commercials.queue_episode("b2")
        commercials.queue_episode("a3")
        db.save_commercials("a3", "done", [])
        self.assertEqual(self.ids(), [])


if __name__ == "__main__":
    unittest.main()
