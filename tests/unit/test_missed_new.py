try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

from app import database as db
from app.main import app
from app.routes import guide, live
from app.sync_service import guide_airing_row

HDR = {"X-TabloView": "1"}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class MissedNewTests(unittest.TestCase):
    """New episodes of Record New series that the Tablo skipped as not new are listed in Scheduled,
    so they can be recorded (a forum user toggled the rule every day to get them recorded)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("guide_shows", "guide_airings"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        db.upsert_guide_show({"path": "/guide/series/1", "title": "Record New", "category": "series", "schedule_rule": "new"})
        db.upsert_guide_show({"path": "/guide/series/2", "title": "Not Recorded", "category": "series", "schedule_rule": "none"})
        soon = datetime.now(timezone.utc) + timedelta(hours=2)

        def a(path, series, state, reason="", new=True, hours=0):
            return {"path": path, "series_path": series, "show_title": path, "air_datetime": iso(soon + timedelta(hours=hours)),
                    "duration": 3600, "is_new": new, "schedule_state": state, "skip_reason": reason}
        db.batch_upsert_guide_airings([
            a("/a/recording", "/guide/series/1", "scheduled"),
            a("/a/missed", "/guide/series/1", "skipped", "not_new"),  # same time: uses no tuner
            a("/a/rerun", "/guide/series/1", "skipped", "not_new", new=False, hours=1),
            a("/a/other_reason", "/guide/series/1", "skipped", "manual", hours=2),
            a("/a/no_rule", "/guide/series/2", "none", hours=3),
        ])

    def test_skip_reason_is_read_from_the_tablo(self):
        row = guide_airing_row("/guide/airings/9", {"schedule": {"state": "skipped", "skip_reason": "not_new"}})
        self.assertEqual((row["schedule_state"], row["skip_reason"]), ("skipped", "not_new"))

    def test_only_new_episodes_skipped_as_not_new(self):
        self.assertEqual([r["path"] for r in db.get_upcoming_recordings()], ["/a/recording"])
        paths = [r["path"] for r in db.get_upcoming_recordings(include_missed_new=True)]
        self.assertEqual(sorted(paths), ["/a/missed", "/a/recording"])

    def test_recording_it_clears_the_reason(self):
        db.update_airing_schedule_states({"/a/missed": "scheduled"})
        rows = {r["path"]: r for r in db.get_upcoming_recordings(include_missed_new=True)}
        self.assertEqual((rows["/a/missed"]["schedule_state"], rows["/a/missed"]["skip_reason"]), ("scheduled", ""))

    def test_scheduled_page_marks_them_and_they_cause_no_conflict(self):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        with mock.patch.object(live, "model_tuner_count", new=mock.AsyncMock(return_value=1)), \
             mock.patch.object(type(guide.tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)):
            data = client.get("/api/guide/upcoming", headers=HDR).json()
        by_path = {r["path"]: r for r in data["recordings"]}
        self.assertEqual(data["missed_new"], 1)
        self.assertTrue(by_path["/a/missed"]["missed_new"])
        self.assertFalse(by_path["/a/recording"]["missed_new"])
        self.assertEqual(data["conflicts"], [])  # one tuner, but the missed one isn't recording


if __name__ == "__main__":
    unittest.main()
