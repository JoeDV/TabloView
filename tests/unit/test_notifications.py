try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import database as db
from app import notifications



def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def recording(ep_id, state="finished", end=60, actual=1875):
    return {"id": ep_id, "show_id": "notify-show", "show_title": "Notify Show", "path": f"/recordings/series/episodes/{ep_id}",
            "title": ep_id, "season_number": 1, "episode_number": int(ep_id[-1]), "duration": 1800,
            "raw_json": {"video_details": {"state": state, "duration": actual, "seek": 15,
                                           "recorded_offsets": {"start": -15, "end": end}}}}


class NotificationTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("shows", "episodes", "guide_airings", "sync_meta"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        db.upsert_show({"id": "notify-show", "title": "Notify Show"})
        self.sent = []
        notifications.set_notifier(lambda title, message: self.sent.append((title, message)))
        self.addCleanup(notifications.set_notifier, None)

    def test_existing_problems_are_remembered_not_announced(self):
        db.upsert_episode(recording("ep1", state="failed", actual=900, end=-900))
        self.assertEqual(notifications.check_recordings(), [])
        self.assertEqual(self.sent, [])

    def test_new_problem_is_announced_once(self):
        notifications.check_recordings()  # first run: nothing yet
        db.upsert_episode(recording("ep2", end=-509, actual=1306))
        self.assertEqual(len(notifications.check_recordings()), 1)
        self.assertEqual(self.sent[0][0], "Recording problem")
        self.assertIn("stopped 8 minutes early", self.sent[0][1])
        notifications.check_recordings()
        self.assertEqual(len(self.sent), 1)

    def test_signal_problems_wording(self):
        ep = {"recording_state": "failed", "actual_duration": 3165, "duration": 1800}
        self.assertIn("lost signal", notifications.describe_problem(ep))

    def test_setting_off_suppresses(self):
        notifications.check_recordings()
        db.upsert_episode(recording("ep3", state="failed", actual=0, end=-1800))
        with mock.patch.object(notifications, "load_settings", return_value={"notifications": False}):
            notifications.check_recordings()
        self.assertEqual(self.sent, [])

    def test_conflict_announced_once_within_horizon(self):
        start = datetime.now(timezone.utc) + timedelta(hours=3)
        db.batch_upsert_guide_airings([
            {"path": f"/c/{i}", "series_path": f"/guide/series/{i}", "show_title": f"Show {i}", "air_datetime": iso(start),
             "duration": 3600, "channel_call_sign": "WAAA", "schedule_state": "scheduled"} for i in range(3)])
        self.assertEqual(len(notifications.check_conflicts(2)), 1)
        self.assertEqual(self.sent[0][0], "Recording conflict")
        self.assertIn("3 recordings but only 2 tuners", self.sent[0][1])
        self.assertEqual(notifications.check_conflicts(2), [])
        self.assertEqual(notifications.check_conflicts(3), [])  # enough tuners: no conflict


    # The Tablo's drive almost full
    def drive(self, pct, total=1000.0):
        return {"connected": True, "total_gb": total, "used_gb": total * pct / 100, "free_gb": total * (100 - pct) / 100,
                "percent_used": pct, "drives": []}

    def test_space_announced_once_per_level(self):
        self.assertEqual(notifications.check_space(self.drive(80)), 0)
        self.assertEqual(notifications.check_space(self.drive(91)), 90)
        self.assertEqual(self.sent[0][0], "Your Tablo's drive is almost full")
        self.assertIn("91% used, 90 GB free", self.sent[0][1])
        self.assertEqual(notifications.check_space(self.drive(93)), 0)  # same level: not again
        self.assertEqual(notifications.check_space(self.drive(96)), 95)
        self.assertEqual(len(self.sent), 2)

    def test_space_said_again_after_it_was_freed(self):
        notifications.check_space(self.drive(92))
        notifications.check_space(self.drive(88))  # still above 85: not reset
        self.assertEqual(notifications.check_space(self.drive(92)), 0)
        notifications.check_space(self.drive(70))
        self.assertEqual(notifications.check_space(self.drive(92)), 90)

    def test_space_names_watched_shows(self):
        for i, (status, size) in enumerate([("Watched", 30 * 1024**3), ("Watched", 12 * 1024**3), ("Unwatched", 99 * 1024**3)]):
            db.upsert_episode({"id": f"sp{i}", "show_id": "notify-show", "show_title": "Notify Show", "path": f"/recordings/series/episodes/sp{i}",
                               "title": f"sp{i}", "status": status, "raw_json": {"video_details": {"size": size}}})
        tips = notifications.deletable_shows()
        self.assertEqual([(t["title"], t["count"]) for t in tips], [("Notify Show", 2)])
        notifications.check_space(self.drive(95))
        self.assertIn("Notify Show (about 42 GB)", self.sent[0][1])

    def test_space_unknown_drive(self):
        self.assertEqual(notifications.check_space({"connected": False, "drives": []}), 0)
        self.assertEqual(notifications.space_level({"connected": True, "total_gb": 0, "percent_used": 0}), 0)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
