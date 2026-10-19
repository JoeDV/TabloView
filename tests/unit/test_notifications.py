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


if __name__ == "__main__":
    unittest.main()
