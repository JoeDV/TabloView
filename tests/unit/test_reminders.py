try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app import extra_channels as xc
from app import reminders


class ReminderTests(unittest.TestCase):
    """Remind me, for More channels (they can't be recorded)."""

    def setUp(self):
        p = mock.patch.object(reminders, "REMINDERS_FILE", Path(tempfile.mkdtemp()) / "reminders.json")
        p.start()
        self.addCleanup(p.stop)
        self.sent = []
        n = mock.patch.object(reminders.notifications, "send", side_effect=lambda t, m: self.sent.append((t, m)))
        n.start()
        self.addCleanup(n.stop)

    def show(self, start):
        return {"channel_key": "abc.news", "channel_id": "x-1", "channel_name": "ABC News Live", "title": "World News",
                "episode_title": None, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "duration": 1800}

    def test_reminded_once_when_it_starts_then_dropped_when_it_ends(self):
        t0 = datetime(2026, 11, 7, 18, 30, tzinfo=timezone.utc)
        r = reminders.add(self.show(t0), now=t0 - timedelta(hours=1))
        self.assertEqual([x["id"] for x in reminders.listing(t0 - timedelta(hours=1))], [r["id"]])
        self.assertEqual(reminders.due(t0 - timedelta(minutes=1)), [])
        self.assertEqual(reminders.notify_due(t0 - timedelta(minutes=1)), [])
        self.assertEqual(len(reminders.due(t0 + timedelta(seconds=40))), 1)
        self.assertEqual(len(reminders.notify_due(t0 + timedelta(seconds=40))), 1)
        self.assertEqual(reminders.notify_due(t0 + timedelta(seconds=70)), [])  # once
        self.assertEqual(self.sent[0][0], "Starting now on ABC News Live")
        self.assertEqual(reminders.due(t0 + timedelta(minutes=6)), [])  # the pages stop showing it
        self.assertEqual(reminders.listing(t0 + timedelta(minutes=31)), [])  # ended: gone

    def test_cancel(self):
        t0 = datetime(2026, 11, 7, 18, 30, tzinfo=timezone.utc)
        r = reminders.add(self.show(t0), now=t0 - timedelta(hours=1))
        reminders.add(self.show(t0), now=t0 - timedelta(hours=1))  # the same show twice: one reminder
        self.assertEqual(len(reminders.listing(t0 - timedelta(hours=1))), 1)
        reminders.remove(r["id"])
        self.assertEqual(reminders.listing(t0 - timedelta(hours=1)), [])


class ExtraMarkTests(unittest.TestCase):
    def test_favorite_and_hide(self):
        store = {}
        with mock.patch.object(xc, "load_settings", side_effect=lambda: dict(store)), \
                mock.patch.object(xc, "save_settings", side_effect=lambda u: store.update(u)):
            self.assertEqual(xc.mark("abc.news", favorite=True), {"favorite": True, "hidden": False})
            c = {"id": "x-1", "name": "ABC News Live", "url": "u", "logo": None, "tvg_id": "abc.news", "number": "", "group": ""}
            self.assertTrue(xc.channel_dict(c)["favorite"])
            self.assertEqual(xc.mark("abc.news", hidden=True), {"favorite": False, "hidden": True})  # hiding unstars
            self.assertTrue(xc.channel_dict(c)["hidden"])
            self.assertEqual(xc.key({**c, "tvg_id": ""}), "name:ABC News Live")


if __name__ == "__main__":
    unittest.main()
