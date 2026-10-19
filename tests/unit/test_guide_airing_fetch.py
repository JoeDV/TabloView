import unittest
from datetime import datetime, timedelta, timezone

from app import database as db


class GuideAiringFetchTests(unittest.TestCase):
    """The guide sync fetches only airings that are new or whose record status can change."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("guide_shows", "guide_airings"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        soon = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.upsert_guide_show({"path": "/guide/series/rule", "title": "Has a rule", "category": "series", "schedule_rule": "new"})
        db.upsert_guide_show({"path": "/guide/series/plain", "title": "No rule", "category": "series", "schedule_rule": "none"})
        db.batch_upsert_guide_airings([
            {"path": "/a/settled", "series_path": "/guide/series/plain", "air_datetime": soon, "schedule_state": "none"},
            {"path": "/a/marked", "series_path": "/guide/series/plain", "air_datetime": soon, "schedule_state": "scheduled"},
            {"path": "/a/rule", "series_path": "/guide/series/rule", "air_datetime": soon, "schedule_state": "none"},
            {"path": "/a/gone", "series_path": "/guide/series/plain", "air_datetime": soon, "schedule_state": "none"},
        ])

    def test_only_new_and_changeable_airings_are_fetched(self):
        listed = ["/a/settled", "/a/marked", "/a/rule", "/a/new"]
        self.assertEqual(db.guide_airings_to_fetch(listed), ["/a/marked", "/a/rule", "/a/new"])

    def test_airings_no_longer_listed_are_removed(self):
        db.guide_airings_to_fetch(["/a/settled"])
        with db.get_connection() as conn:
            left = {r["path"] for r in conn.execute("SELECT path FROM guide_airings")}
        self.assertEqual(left, {"/a/settled"})


if __name__ == "__main__":
    unittest.main()
