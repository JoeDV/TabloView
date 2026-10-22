try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import database as db
from app.main import app
from app.tablo_client import tablo_manager

HDR = {"X-TabloView": "1"}


def add_episode(eid, show="s1", protected=False):
    raw = {"user_info": {"protected": protected}, "video_details": {"state": "finished", "duration": 1800}}
    db.upsert_episode({"id": eid, "show_id": show, "show_title": f"Show {show}", "path": f"/recordings/{eid}",
                       "title": eid, "air_date": "2026-10-20T00:00Z", "duration": 1800, "raw_json": json.dumps(raw)})


class WatchListTests(unittest.TestCase):
    """Recordings from any show, watched one after another; finished ones come off the list and,
    when asked, are deleted from the Tablo (never protected ones)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("episodes", "watch_list"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        for eid, show in (("ep_a", "s1"), ("ep_b", "s2"), ("ep_c", "s1")):
            add_episode(eid, show)
        add_episode("ep_kept", "s2", protected=True)
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.tablo_delete = mock.AsyncMock(return_value=True)
        for p in (mock.patch.object(tablo_manager, "delete_airing", new=self.tablo_delete),
                  mock.patch.object(type(tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True))):
            p.start()
            self.addCleanup(p.stop)

    def ids(self):
        return [e["id"] for e in self.client.get("/api/watchlist").json()["episodes"]]

    def test_add_in_order_across_shows_without_duplicates(self):
        self.client.post("/api/watchlist", json={"episode_ids": ["ep_b", "ep_a"]}, headers=HDR)
        r = self.client.post("/api/watchlist", json={"episode_ids": ["ep_a", "ep_c", "nope"]}, headers=HDR).json()
        self.assertEqual(r["added"], 1)
        self.assertEqual(self.ids(), ["ep_b", "ep_a", "ep_c"])

    def test_reorder_and_remove(self):
        self.client.post("/api/watchlist", json={"episode_ids": ["ep_a", "ep_b", "ep_c"]}, headers=HDR)
        self.client.put("/api/watchlist", json={"episode_ids": ["ep_c", "ep_a"]}, headers=HDR)
        self.assertEqual(self.ids(), ["ep_c", "ep_a"])
        self.client.delete("/api/watchlist/ep_c", headers=HDR)
        self.assertEqual(self.ids(), ["ep_a"])

    def test_finished_and_kept(self):
        self.client.post("/api/watchlist", json={"episode_ids": ["ep_a", "ep_b"]}, headers=HDR)
        r = self.client.post("/api/watchlist/ep_a/finished", json={"delete": False}, headers=HDR).json()
        self.assertFalse(r["deleted"])
        self.tablo_delete.assert_not_called()
        self.assertEqual(self.ids(), ["ep_b"])
        self.assertIsNotNone(db.get_episode_by_id("ep_a"))

    def test_finished_and_deleted(self):
        self.client.post("/api/watchlist", json={"episode_ids": ["ep_a"]}, headers=HDR)
        r = self.client.post("/api/watchlist/ep_a/finished", json={"delete": True}, headers=HDR).json()
        self.assertTrue(r["deleted"])
        self.tablo_delete.assert_awaited_once_with("/recordings/ep_a")
        self.assertIsNone(db.get_episode_by_id("ep_a"))
        self.assertEqual(self.ids(), [])

    def test_protected_recordings_are_never_deleted(self):
        r = self.client.post("/api/watchlist/ep_kept/finished", json={"delete": True}, headers=HDR).json()
        self.assertEqual((r["deleted"], r["protected"]), (False, True))
        self.tablo_delete.assert_not_called()
        self.assertIsNotNone(db.get_episode_by_id("ep_kept"))

    def test_a_refused_delete_is_reported_not_raised(self):
        self.tablo_delete.return_value = False
        r = self.client.post("/api/watchlist/ep_a/finished", json={"delete": True}, headers=HDR).json()
        self.assertFalse(r["deleted"])
        self.assertIn("refused", r["error"])
        self.assertIsNotNone(db.get_episode_by_id("ep_a"))

    def test_recordings_deleted_elsewhere_drop_off(self):
        self.client.post("/api/watchlist", json={"episode_ids": ["ep_a", "ep_b"]}, headers=HDR)
        db.delete_episode("ep_a")
        self.assertEqual(self.ids(), ["ep_b"])


if __name__ == "__main__":
    unittest.main()
