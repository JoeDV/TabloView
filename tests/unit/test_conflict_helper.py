import unittest
from datetime import datetime, timedelta, timezone

from app.schedule_check import find_alternatives, same_episode


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


T0 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)


def airing(path, series, start, se=(1, 1), title="Pilot", state="scheduled", minutes=60):
    return {"path": path, "series_path": series, "show_title": series.title(), "episode_title": title,
            "season_number": se[0], "episode_number": se[1], "air_datetime": iso(start), "duration": minutes * 60,
            "channel_call_sign": "WAAA", "channel_network": "ABC", "schedule_state": state}


class SameEpisodeTests(unittest.TestCase):
    def test_matches_by_numbers(self):
        self.assertTrue(same_episode(airing("/a", "s", T0), airing("/b", "s", T0, title="Other")))
        self.assertFalse(same_episode(airing("/a", "s", T0), airing("/b", "s", T0, se=(1, 2))))

    def test_matches_by_title_without_numbers(self):
        self.assertTrue(same_episode(airing("/a", "s", T0, se=(0, 0)), airing("/b", "s", T0, se=(0, 0))))
        self.assertFalse(same_episode(airing("/a", "s", T0, se=(0, 0), title=""), airing("/b", "s", T0, se=(0, 0), title="")))

    def test_never_matches_itself_or_another_series(self):
        a = airing("/a", "s", T0)
        self.assertFalse(same_episode(a, a))
        self.assertFalse(same_episode(a, airing("/b", "other", T0)))


class FindAlternativesTests(unittest.TestCase):
    def setUp(self):
        # Three shows at the same hour, two tuners: a conflict
        self.scheduled = [airing("/x1", "x", T0), airing("/y1", "y", T0), airing("/z1", "z", T0)]

    def test_rerun_at_a_free_time_resolves_the_conflict(self):
        candidates = [airing("/x2", "x", T0 + timedelta(hours=5), state="none")]
        [c] = find_alternatives(self.scheduled, candidates, tuners=2)
        x = next(r for r in c["recordings"] if r["path"] == "/x1")
        self.assertEqual([a["path"] for a in x["alternatives"]], ["/x2"])
        self.assertTrue(x["alternatives"][0]["resolves"])

    def test_rerun_that_overlaps_other_recordings_does_not_resolve(self):
        busy = T0 + timedelta(hours=5)
        scheduled = self.scheduled + [airing("/p1", "p", busy), airing("/q1", "q", busy)]
        candidates = [airing("/x2", "x", busy, state="none")]
        conflicts = find_alternatives(scheduled, candidates, tuners=2)
        x = next(r for r in conflicts[0]["recordings"] if r["path"] == "/x1")
        self.assertFalse(x["alternatives"][0]["resolves"])

    def test_already_scheduled_and_past_airings_are_not_offered(self):
        candidates = [airing("/x2", "x", T0 + timedelta(hours=5), state="scheduled"),
                      airing("/x3", "x", datetime.now(timezone.utc) - timedelta(hours=2), state="none")]
        [c] = find_alternatives(self.scheduled, candidates, tuners=2)
        self.assertTrue(all(not r["alternatives"] for r in c["recordings"]))

    def test_no_conflicts_no_results(self):
        self.assertEqual(find_alternatives(self.scheduled, [], tuners=4), [])


if __name__ == "__main__":
    unittest.main()
