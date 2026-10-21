try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.routes import guide, live


HDR = {"X-TabloView": "1"}


def airing(path, hour, state):
    return {"path": path, "series_path": "/guide/series/1", "show_title": f"Show {path}", "episode_title": "",
            "season_number": 1, "episode_number": int(path[-1]), "air_datetime": f"2030-01-01T{hour:02d}:00:00Z",
            "duration": 3600, "channel_call_sign": "WAAA", "channel_network": "CBS", "qualifiers": [],
            "is_new": True, "is_premiere": False, "schedule_state": state}


class ConflictedRecordingTests(unittest.TestCase):
    """Recordings the Tablo won't make (no tuner free) are listed in Scheduled, marked Won't record,
    as the Tablo's own apps list them. (NCIS night on a 2-tuner Tablo looked like they had vanished.)"""

    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def upcoming(self, rows):
        with mock.patch.object(guide, "get_upcoming_recordings", return_value=rows) as get, \
             mock.patch.object(live, "model_tuner_count", new=mock.AsyncMock(return_value=2)), \
             mock.patch.object(type(guide.tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)):
            data = self.client.get("/api/guide/upcoming", headers=HDR).json()
        get.assert_called_once_with(include_conflicted=True, include_missed_new=True)
        return data

    def test_three_shows_at_once_on_two_tuners(self):
        data = self.upcoming([airing("/e/1", 20, "scheduled"), airing("/e/2", 20, "scheduled"),
                              airing("/e/3", 20, "conflicted")])
        by_path = {r["path"]: r for r in data["recordings"]}
        self.assertEqual(data["wont_record"], 1)
        self.assertTrue(by_path["/e/3"]["wont_record"])
        self.assertFalse(by_path["/e/1"]["wont_record"])
        self.assertEqual(len(data["conflicts"]), 1)  # and the 8 PM clash is now visible
        self.assertEqual(data["conflicts"][0]["count"], 3)

    def test_a_conflict_the_tablo_reports_is_marked_even_without_an_overlap_we_can_see(self):
        data = self.upcoming([airing("/e/1", 20, "conflicted")])
        self.assertTrue(data["recordings"][0]["wont_record"])
        self.assertTrue(data["recordings"][0]["conflict"])


if __name__ == "__main__":
    unittest.main()
