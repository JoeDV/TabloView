try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import alerts, notifications
from app import database as db

NOW = datetime.now(timezone.utc)


def airing(path, show, episode="", hours=24, minutes=60, state="none"):
    t = (NOW + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")
    return {"path": path, "series_path": f"/guide/series/{path[-1]}", "show_title": show, "episode_title": episode,
            "air_datetime": t, "duration": minutes * 60, "channel_call_sign": "WCAU", "schedule_state": state}


class GuideAlertTests(unittest.TestCase):
    """Words to watch for in the guide (a team, a movie, a special): matches show on Home with
    Record, and new ones bring a notification."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM guide_airings")
            conn.execute("DELETE FROM sync_meta WHERE key = 'notified_alerts'")
            conn.commit()
        db.batch_upsert_guide_airings([
            airing("/guide/e/1", "NFL Football", "Philadelphia Eagles at Dallas Cowboys"),
            airing("/guide/e/2", "The Wizard of Oz", hours=48, state="scheduled"),
            airing("/guide/e/3", "Seagles Weekly"),                     # not the word Eagles
            airing("/guide/e/4", "Eagles Postgame", hours=-3),          # over already
            airing("/guide/e/5", "Jeopardy!", "Jeopardy! Masters Finals", hours=2),
        ])
        self.saved = {}
        for p in (mock.patch.object(alerts, "load_settings", side_effect=lambda: dict(self.saved)),
                  mock.patch.object(alerts, "save_settings", side_effect=lambda u: self.saved.update(u))):
            p.start()
            self.addCleanup(p.stop)

    def test_whole_words_in_show_or_episode_titles_still_to_come(self):
        got = {m["path"]: m["alert"] for m in alerts.matches(["eagles", "wizard of oz", "Jeopardy! Masters"])}
        self.assertEqual(got, {"/guide/e/1": "eagles", "/guide/e/2": "wizard of oz", "/guide/e/5": "Jeopardy! Masters"})
        found = alerts.matches(["Wizard of Oz"])
        self.assertTrue(found[0]["scheduled"])
        self.assertEqual([m["path"] for m in alerts.matches(["Eagles", "Jeopardy!"])], ["/guide/e/5", "/guide/e/1"])  # soonest first

    def test_add_and_remove_words(self):
        self.assertEqual(alerts.add("  Eagles  "), ["Eagles"])
        self.assertEqual(alerts.add("eagles"), ["Eagles"])  # already there
        with self.assertRaises(alerts.AlertError):
            alerts.add("x")
        self.assertEqual(alerts.add("Wizard of Oz"), ["Eagles", "Wizard of Oz"])
        self.assertEqual(alerts.remove("EAGLES"), ["Wizard of Oz"])

    def test_one_notification_for_new_matches_not_the_first_time(self):
        self.saved["guide_alerts"] = ["Eagles"]
        with mock.patch.object(notifications, "send") as send:
            self.assertEqual(alerts.notify_new(), [])   # the first time: what's there is taken as known
            send.assert_not_called()
            self.saved["guide_alerts"] = ["Eagles", "Jeopardy! Masters"]
            new = alerts.notify_new()
            self.assertEqual([m["path"] for m in new], ["/guide/e/5"])
            send.assert_called_once()
            self.assertIn("Jeopardy!", send.call_args[0][1])
            alerts.notify_new()                         # nothing new since
            send.assert_called_once()

    def test_set_to_record_already_isnt_announced(self):
        self.saved["guide_alerts"] = ["Eagles"]
        alerts.notify_new()
        self.saved["guide_alerts"] = ["Eagles", "Wizard of Oz"]
        with mock.patch.object(notifications, "send") as send:
            self.assertEqual(alerts.notify_new(), [])
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
