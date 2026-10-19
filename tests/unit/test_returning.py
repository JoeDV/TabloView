import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import database as db
from app import returning


class ReturningTests(unittest.TestCase):
    """A series you recorded before, with a season premiere coming and no recording rule: it's back."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("guide_shows", "guide_airings", "shows", "sync_meta"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        soon = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%MZ")
        for path, title, rule in (("/guide/series/back", "Back Show", "none"),
                                  ("/guide/series/ruled", "Already Recording", "new"),
                                  ("/guide/series/stranger", "Never Recorded", "none")):
            db.upsert_guide_show({"path": path, "title": title, "category": "series", "schedule_rule": rule})
            db.batch_upsert_guide_airings([{"path": f"{path}/ep", "series_path": path, "show_title": title,
                                            "air_datetime": soon, "duration": 1800, "season_number": 4,
                                            "episode_number": 1, "is_new": 1, "is_premiere": 1}])
        # In the library (recorded before): the first two
        for i, path in enumerate(("/guide/series/back", "/guide/series/ruled")):
            db.upsert_show({"id": f"s{i}", "title": path, "raw_json": {"guide_path": path}})

    def test_only_recorded_before_and_not_set_to_record(self):
        returning.remember_recorded()
        found = returning.find()
        self.assertEqual([g["title"] for g in found], ["Back Show"])
        self.assertEqual(found[0]["premiere_season"], 4)

    def test_still_remembered_after_its_recordings_are_deleted(self):
        returning.remember_recorded()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM shows")
            conn.commit()
        self.assertEqual([g["title"] for g in returning.find()], ["Back Show"])

    def test_announced_once(self):
        with mock.patch("app.notifications.send") as send:
            self.assertEqual(len(returning.check()), 1)
            self.assertEqual(returning.check(), [])
        send.assert_called_once()
        self.assertIn("Back Show", send.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
