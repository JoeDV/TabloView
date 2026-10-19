import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import cleanup

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def ep(id, show="jeopardy", protected=False):
    return {"id": id, "show_id": show, "show_title": show.title(), "title": id, "path": f"/recordings/series/episodes/{id}",
            "protected": protected}


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.meta = {}
        self.settings = {"cleanup_days": {}}
        patches = [
            mock.patch.object(cleanup, "get_sync_meta", side_effect=lambda k: self.meta.get(k)),
            mock.patch.object(cleanup, "set_sync_meta", side_effect=lambda k, v: self.meta.__setitem__(k, v)),
            mock.patch.object(cleanup, "load_settings", side_effect=lambda: dict(self.settings)),
            mock.patch.object(cleanup, "save_settings", side_effect=lambda u: self.settings.update(u)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_first_seen_watched_is_remembered_and_forgotten_when_unwatched(self):
        since = cleanup.track_watched([ep("a"), ep("b")], now=NOW)
        self.assertEqual(since["a"], NOW.isoformat())
        later = cleanup.track_watched([ep("a")], now=NOW + timedelta(days=2))
        self.assertEqual(later, {"a": NOW.isoformat()})  # keeps the first time; b no longer watched

    def test_due_after_the_shows_days_and_never_protected(self):
        watched = [ep("old"), ep("new"), ep("locked", protected=True), ep("other", show="news")]
        since = {"old": (NOW - timedelta(days=8)).isoformat(), "new": (NOW - timedelta(days=2)).isoformat(),
                 "locked": (NOW - timedelta(days=30)).isoformat(), "other": (NOW - timedelta(days=30)).isoformat()}
        due = cleanup.due(watched, since, {"jeopardy": 7}, now=NOW)
        self.assertEqual([e["id"] for e in due], ["old"])

    def test_rules_set_and_cleared(self):
        cleanup.set_rule("jeopardy", 7)
        self.assertEqual(cleanup.rules(), {"jeopardy": 7})
        cleanup.set_rule("jeopardy", None)
        self.assertEqual(cleanup.rules(), {})

    def test_run_deletes_due_recordings_on_the_tablo(self):
        self.settings["cleanup_days"] = {"jeopardy": 1}
        self.meta["watched_since"] = '{"a": "2020-01-01T00:00:00+00:00"}'
        tablo = mock.MagicMock()
        tablo.delete_airing = mock.AsyncMock(return_value=True)
        with mock.patch.object(cleanup, "get_watched_episodes", return_value=[ep("a"), ep("b")]), \
                mock.patch.object(cleanup, "delete_episode") as deleted, \
                mock.patch.object(cleanup, "recalculate_show_stats"), \
                mock.patch("app.tablo_client.tablo_manager", tablo), \
                mock.patch("app.notifications.send") as sent:
            self.assertEqual(asyncio.run(cleanup.run()), 1)
        tablo.delete_airing.assert_awaited_once_with("/recordings/series/episodes/a")
        deleted.assert_called_once_with("a")
        sent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
