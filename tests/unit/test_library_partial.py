import asyncio
import json
import unittest
from unittest import mock

import httpx

from app import database as db
from app import sync_service as sync
from app.sync_service import LibrarySyncService


def recording(n):
    return {"object_id": n, "series_path": "/recordings/series/1",
            "episode": {"title": f"Ep {n}", "number": n, "season_number": 1},
            "airing_details": {"datetime": f"2026-10-{n:02d}T00:00Z", "duration": 1800, "show_title": "Show One",
                               "channel": {"channel": {"call_sign": "WAAA"}}},
            "user_info": {"watched": False}}


class Tablo:
    """10 recordings; the Tablo stops answering after the first batch of 4 when refuse is set."""

    def __init__(self, refuse, count=10):
        self.refuse = refuse
        self.paths = [f"/recordings/series/episodes/{n}" for n in range(1, count + 1)]

    async def __call__(self, method, path, body=""):
        if path == "/recordings/series?lh":
            return httpx.Response(200, json=[])
        if path == "/recordings/airings?lh":  # with streaming recordings
            return httpx.Response(200, json=self.paths)
        if path == "/batch":
            wanted = json.loads(body)
            if self.refuse and self.paths[4] in wanted:
                raise httpx.ConnectError("All connection attempts failed")
            return httpx.Response(200, json={p: recording(int(p.rsplit("/", 1)[1])) for p in wanted})
        raise AssertionError(path)


class LibraryPartialSyncTests(unittest.TestCase):
    """A library sync the Tablo cuts short keeps the recordings it didn't get back (it used to treat
    them as deleted and drop them from the Library until the next sync)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM shows")
            conn.execute("DELETE FROM episodes")
            conn.commit()
        for p in (mock.patch.object(sync, "TABLO_BREAK_SECONDS", 0), mock.patch.object(sync, "BATCH_PAUSE", 0),
                  mock.patch.object(sync, "BATCH_SIZE", 4), mock.patch.object(sync, "check_all", new=mock.AsyncMock()),
                  mock.patch.object(sync.cleanup, "run", new=mock.AsyncMock()),
                  mock.patch.object(sync.rerecord, "run", new=mock.AsyncMock()),
                  mock.patch.object(sync.signal_health, "check")):
            p.start()
            self.addCleanup(p.stop)

    def sync(self, refuse, count=10):
        with mock.patch.object(sync.tablo_manager, "request_bulk", new=Tablo(refuse, count)), \
             mock.patch.object(type(sync.tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)):
            asyncio.run(LibrarySyncService().sync_library(include_guide=False))
        with db.get_connection() as conn:
            eps = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            count = conn.execute("SELECT episode_count FROM shows WHERE id = 'show-one'").fetchone()
        return eps, count[0] if count else None

    def test_a_cut_short_sync_keeps_the_rest_of_the_library(self):
        self.assertEqual(self.sync(refuse=False), (10, 10))
        self.assertEqual(self.sync(refuse=True), (10, 10))  # 4 came back; the other 6 are kept and counted

    def test_a_complete_sync_still_removes_deleted_recordings(self):
        self.sync(refuse=False)
        self.assertEqual(self.sync(refuse=False, count=7), (7, 7))  # 3 deleted on the Tablo


if __name__ == "__main__":
    unittest.main()
