import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import rerecord

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def rec(id, incomplete=True, days_ago=1, episode=5):
    return {"id": id, "show_id": "show", "show_title": "Show", "series_path": "/guide/series/1",
            "season_number": 2, "episode_number": episode, "episode_title": "", "incomplete": incomplete,
            "air_date": iso(NOW - timedelta(days=days_ago)), "duration": 1800}


def airing(path, hours, episode=5, state="none"):
    return {"path": path, "show_title": "Show", "series_path": "/guide/series/1", "season_number": 2, "episode_number": episode,
            "episode_title": "", "air_datetime": iso(NOW + timedelta(hours=hours)), "duration": 1800,
            "schedule_state": state}


class RerecordTests(unittest.TestCase):
    def pick(self, recs, airings, upcoming=(), handled=None, tuners=2):
        with mock.patch.object(rerecord, "get_series_airings", return_value=list(airings)), \
                mock.patch.object(rerecord, "get_upcoming_recordings", return_value=list(upcoming)):
            return rerecord.pick(recs, handled or {}, tuners, now=NOW)

    def test_earliest_rerun_of_a_recent_failure(self):
        plans = self.pick([rec("a")], [airing("/x/late", 48), airing("/x/early", 5), airing("/x/other", 1, episode=6)])
        self.assertEqual([p["airing"]["path"] for p in plans], ["/x/early"])

    def test_skips_a_rerun_that_would_need_another_tuner(self):
        busy = [airing("/b/1", 5, episode=90, state="scheduled"), airing("/b/2", 5, episode=91, state="scheduled")]
        plans = self.pick([rec("a")], [airing("/x/early", 5), airing("/x/late", 48)], upcoming=busy)
        self.assertEqual([p["airing"]["path"] for p in plans], ["/x/late"])

    def test_leaves_alone_what_doesnt_need_it(self):
        self.assertEqual(self.pick([rec("a", incomplete=False)], [airing("/x", 5)]), [])  # recorded fine
        self.assertEqual(self.pick([rec("a", days_ago=30)], [airing("/x", 5)]), [])  # too long ago
        self.assertEqual(self.pick([rec("a")], [airing("/x", 5)], handled={"a": "/x"}), [])  # done before
        self.assertEqual(self.pick([rec("a"), rec("b", incomplete=False, days_ago=3)], [airing("/x", 5)]), [])  # have a good copy
        self.assertEqual(self.pick([rec("a")], [airing("/x", 5, state="scheduled")]), [])  # already set to record


if __name__ == "__main__":
    unittest.main()
