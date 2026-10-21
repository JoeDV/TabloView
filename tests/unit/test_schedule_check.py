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

    def on(self, channel, start_min, minutes):
        a = airing(f"{channel}@{start_min}", start_min / 60, minutes, base=datetime.now(timezone.utc))
        a["channel_identifier"] = channel
        return a

    def test_recordings_that_follow_on_the_same_channels_reuse_their_tuners(self):
        # 4-tuner Tablo: two recording now, two more in 15 min on the same two channels. Tuning a third
        # channel needs 3 tuners at most (a user got "Not enough tuners" for every other channel)
        upcoming = [self.on("A", -45, 60), self.on("B", -45, 60), self.on("A", 15, 60), self.on("B", 15, 60)]
        r = live_tv_check(upcoming, total=4, in_use=2, held=0, recording=2)
        self.assertFalse(r["warn"])

    def test_a_new_channel_recording_still_warns(self):
        # A and B still recording when C starts: 3 recording + the new channel = 4 fits; with a held
        # tuner as well it doesn't
        upcoming = [self.on("A", -45, 90), self.on("B", -45, 90), self.on("C", 15, 60)]
        self.assertFalse(live_tv_check(upcoming, total=4, in_use=2, held=0, recording=2)["warn"])
        self.assertTrue(live_tv_check(upcoming, total=4, in_use=3, held=1, recording=2)["warn"])

    def test_two_recordings_on_one_channel_use_one_tuner(self):
        upcoming = [self.on("A", 10, 60), self.on("A", 10, 60), self.on("B", 10, 60), self.on("C", 10, 60)]
        self.assertFalse(live_tv_check(upcoming, total=4, in_use=0, held=0, recording=0)["warn"])
        upcoming.append(self.on("D", 10, 60))
        self.assertTrue(live_tv_check(upcoming, total=4, in_use=0, held=0, recording=0)["warn"])


if __name__ == "__main__":
    unittest.main()
