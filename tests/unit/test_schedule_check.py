import unittest
from datetime import datetime, timedelta, timezone

from app.schedule_check import find_conflicts, peak_overlap, live_tv_check

BASE = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)


def airing(title, start_hours, minutes=60, base=BASE):
    start = base + timedelta(hours=start_hours)
    return {"path": title, "show_title": title, "air_datetime": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "duration": minutes * 60}


class ConflictTests(unittest.TestCase):
    def test_more_overlaps_than_tuners_is_a_conflict(self):
        sched = [airing(t, 0) for t in "ABCDE"]
        conflicts = find_conflicts(sched, 4)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["count"], 5)
        self.assertEqual(conflicts[0]["titles"], list("ABCDE"))
        self.assertTrue(all(a["conflict"] for a in sched))

    def test_back_to_back_shows_do_not_overlap(self):
        sched = [airing(t, 0) for t in "ABCD"] + [airing("Next", 1)]
        self.assertEqual(find_conflicts(sched, 4), [])
        self.assertFalse(sched[-1]["conflict"])

    def test_enough_tuners_means_no_conflict(self):
        self.assertEqual(find_conflicts([airing(t, 0) for t in "ABCDE"], 6), [])

    def test_conflict_window_covers_only_the_overlap(self):
        sched = [airing(t, 0) for t in "ABCD"] + [airing("Late", 0.5, 60)]
        (c,) = find_conflicts(sched, 4)
        self.assertEqual((c["start"], c["end"]), ("2026-10-20T00:30:00Z", "2026-10-20T01:00:00Z"))

    def test_peak_overlap(self):
        self.assertEqual(peak_overlap([airing("A", 0), airing("B", 0.5), airing("C", 2)]), 2)


class LiveTvCheckTests(unittest.TestCase):
    def soon(self, minutes_from_now):
        return airing("Soon", minutes_from_now / 60, base=datetime.now(timezone.utc))

    def test_warns_when_tuning_leaves_too_few_tuners(self):
        r = live_tv_check([self.soon(30)], total=4, in_use=3, held=2)
        self.assertTrue(r["warn"])
        self.assertEqual(r["free_after_tuning"], 0)

    def test_no_warning_with_spare_tuners(self):
        self.assertFalse(live_tv_check([self.soon(30)], total=4, in_use=1, held=0)["warn"])

    def test_recordings_beyond_horizon_are_ignored(self):
        self.assertFalse(live_tv_check([self.soon(180)], total=4, in_use=3, held=0)["warn"])

    def test_all_tuners_busy(self):
        self.assertTrue(live_tv_check([], total=4, in_use=4, held=1)["no_free_tuner"])


if __name__ == "__main__":
    unittest.main()
