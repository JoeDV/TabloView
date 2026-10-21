try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone

from app import database as db



def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("shows", "episodes", "guide_shows", "guide_airings"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        now = datetime.now(timezone.utc)
        # Guide: one airing show that's recording, one airing show not recording, one recording but off the air
        for path, title, rule in (("/guide/series/1", "Airing Recorded", "new"),
                                  ("/guide/series/2", "Airing Not Recorded", "none"),
                                  ("/guide/series/3", "Off Season", "all")):
            db.upsert_guide_show({"path": path, "title": title, "category": "series", "schedule_rule": rule, "genres": ["Drama"]})
        db.batch_upsert_guide_airings([
            {"path": "/a/1", "series_path": "/guide/series/1", "show_title": "Airing Recorded", "air_datetime": iso(now + timedelta(hours=2)),
             "duration": 3600, "channel_call_sign": "WAAA", "channel_identifier": "S1_002_01", "schedule_state": "scheduled"},
            {"path": "/a/2", "series_path": "/guide/series/2", "show_title": "Airing Not Recorded", "air_datetime": iso(now + timedelta(hours=3)),
             "duration": 1800, "channel_call_sign": "WBBB", "channel_identifier": "S2_004_01", "schedule_state": "none"},
            {"path": "/a/old", "series_path": "/guide/series/1", "show_title": "Airing Recorded", "air_datetime": iso(now - timedelta(hours=10)),
             "duration": 1800, "channel_call_sign": "WAAA", "schedule_state": "scheduled"},
            # Asked for by a rule, but the Tablo has no tuner free for it
            {"path": "/a/3", "series_path": "/guide/series/1", "show_title": "Airing Recorded", "air_datetime": iso(now + timedelta(hours=4)),
             "duration": 3600, "channel_call_sign": "WCCC", "schedule_state": "conflicted"},
        ])
        # Library: one show, two episodes
        db.upsert_show({"id": "show-1", "title": "Show One", "episode_count": 2, "unwatched_count": 2})
        for i, pos in ((1, 0), (2, 900)):
            db.upsert_episode({"id": f"ep_{i}", "show_id": "show-1", "show_title": "Show One", "path": f"/recordings/series/episodes/{i}",
                               "title": f"Ep {i}", "air_date": iso(now - timedelta(days=i)), "duration": 3600, "position": pos})

    def titles(self, **kw):
        return {g["title"] for g in db.get_guide_shows(limit=500, **kw)}

    def test_browsing_only_lists_shows_with_upcoming_airings(self):
        self.assertEqual(self.titles(), {"Airing Recorded", "Airing Not Recorded"})

    def test_recording_filter_includes_off_season_rules(self):
        self.assertEqual(self.titles(rule="scheduled"), {"Airing Recorded", "Off Season"})

    def test_search_finds_off_season_series_you_record(self):
        self.assertEqual(self.titles(search="season"), {"Off Season"})

    def test_old_airings_are_purged(self):
        with db.get_connection() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM guide_airings WHERE path = '/a/old'").fetchone())

    def test_upcoming_recordings_only_include_scheduled(self):
        self.assertEqual([r["path"] for r in db.get_upcoming_recordings()], ["/a/1"])

    def test_upcoming_recordings_can_include_ones_the_tablo_wont_record(self):
        rows = db.get_upcoming_recordings(include_conflicted=True)
        self.assertEqual([(r["path"], r["schedule_state"]) for r in rows], [("/a/1", "scheduled"), ("/a/3", "conflicted")])

    def test_epg_groups_by_channel_identifier(self):
        epg = db.get_epg_schedule(hours=6)
        self.assertIn("S1_002_01", epg["airings_by_identifier"])
        self.assertEqual(epg["airings_by_identifier"]["S1_002_01"][0]["genres"], ["Drama"])

    def test_guide_pages_start_on_the_half_hour(self):
        # Paging Live TV asked for e.g. 7:37, which made every column odd and moved with the clock
        epg = db.get_epg_schedule(hours=3, start_iso="2026-10-20T19:37:12Z")
        self.assertEqual(epg["window_start"], "2026-10-20T19:30:00Z")
        self.assertEqual([s["iso"][11:16] for s in epg["slots"]], ["19:30", "20:00", "20:30", "21:00", "21:30", "22:00"])
        self.assertEqual(db.get_epg_schedule(hours=3, start_iso="2026-10-20T20:05:00Z")["window_start"], "2026-10-20T20:00:00Z")

    def test_stale_rules_are_cleared(self):
        db.upsert_guide_show({"path": "/guide/series/9", "title": "Removed On TV", "category": "series", "schedule_rule": "new"})
        cleared = db.clear_stale_schedule_rules("series", ["/guide/series/1", "/guide/series/3"])
        self.assertEqual(cleared, 1)
        self.assertEqual(db.get_guide_show_by_path("/guide/series/9")["schedule_rule"], "none")

    def test_progress_and_watched(self):
        self.assertEqual([e["id"] for e in db.get_in_progress_episodes()], ["ep_2"])
        db.set_episode_progress("ep_2", watched=True)
        self.assertEqual(db.get_in_progress_episodes(), [])
        self.assertEqual(db.get_show_by_id("show-1")["unwatched_count"], 1)
        db.set_episode_progress("ep_2", position=1200)  # saving a position marks it unwatched again (as on the Tablo)
        self.assertEqual(db.get_show_by_id("show-1")["unwatched_count"], 2)


if __name__ == "__main__":
    unittest.main()
