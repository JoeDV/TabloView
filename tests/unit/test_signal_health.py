import unittest
from datetime import datetime, timezone

from app import database as db
from app import signal_health

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def rec(id, channel, call, air, problem=False, reason=None):
    return (id, "Show", air, channel, call, "NBC", "failed" if problem else "finished", 1 if problem else 0, reason, "x")


class SignalHealthTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM recording_history")
            rows = [rec(f"a{i}", "13.1", "WTHR", f"2026-10-{10 + i:02d}T23:30Z", problem=i < 3, reason="weak_signal") for i in range(6)]
            rows += [rec(f"b{i}", "29.1", "WTTK", f"2026-10-{10 + i:02d}T15:00Z") for i in range(5)]
            rows += [rec("old", "8.1", "WISH", "2026-06-01T23:30Z", problem=True, reason="weak_signal")]  # outside 60 days
            conn.executemany("INSERT INTO recording_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()

    def test_a_channel_that_keeps_failing_is_flagged_with_why(self):
        report = signal_health.report(now=NOW)
        top = report[0]
        self.assertEqual((top["channel"], top["recordings"], top["problems"], top["status"]), ("13.1", 6, 3, "frequent"))
        self.assertEqual(top["reason"], "weak signal")
        self.assertTrue(top["signal"])
        self.assertIsNotNone(top["when"])  # all at the same local hour

    def test_healthy_channels_and_the_window(self):
        report = {c["channel"]: c for c in signal_health.report(now=NOW)}
        self.assertEqual(report["29.1"]["status"], "ok")
        self.assertNotIn("8.1", report)  # its only recording is older than the report window

    def test_failure_reason_from_the_tablo_error(self):
        self.assertEqual(signal_health._reason({"details": "weak_signal", "description": 'error=[".../recording/unableToTune"]'}), "unableToTune")
        self.assertEqual(signal_health._reason({"details": "weak_signal", "description": ""}), "weak_signal")


if __name__ == "__main__":
    unittest.main()
