import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx

from app import database as db
from app import sync_service as sync
from app.sync_service import LibrarySyncService, fetch_objects


def airing(path):
    return {"path": path, "series_path": "/guide/series/1", "qualifiers": [], "episode": {"title": path},
            "airing_details": {"datetime": "2099-01-01T00:00Z", "duration": 1800, "show_title": "Show"}}


class FakeTablo:
    """Answers POST /batch (optionally refusing once, or rejecting batches) and single GETs."""

    def __init__(self, airing_paths, refuse_once_at=None, batch_status=200):
        self.airing_paths = airing_paths
        self.refuse_once_at = refuse_once_at
        self.batch_status = batch_status
        self.requests = []

    async def __call__(self, method, path, body=""):
        self.requests.append((method, path))
        if path == "/guide/airings":
            return httpx.Response(200, json=self.airing_paths)
        if path == "/batch":
            wanted = json.loads(body)
            if self.refuse_once_at in wanted:
                self.refuse_once_at = None
                raise httpx.ConnectError("All connection attempts failed")
            if self.batch_status != 200:
                return httpx.Response(self.batch_status, json={"error": "nope"})
            return httpx.Response(200, json={p: airing(p) for p in wanted})
        if path.startswith("/guide/airings/"):
            return httpx.Response(200, json=airing(path))
        return httpx.Response(200, json=[])  # show catalog lists: nothing


class GuideLoadTests(unittest.TestCase):
    """The Tablo makes a new connection per request and refuses connections for a minute after a burst,
    so objects are fetched 50 per POST /batch, with progress, and a refusal is waited out."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM guide_airings")
            conn.execute("DELETE FROM sync_meta")
            conn.commit()
        for p in (mock.patch.object(sync, "TABLO_BREAK_SECONDS", 0), mock.patch.object(sync, "BATCH_PAUSE", 0)):
            p.start()
            self.addCleanup(p.stop)

    def test_first_load_in_batches_with_progress_and_waiting_out_a_refusal(self):
        paths = [f"/guide/airings/{i}" for i in range(320)]
        tablo = FakeTablo(paths, refuse_once_at=paths[150])
        service = LibrarySyncService()
        progress = []
        real_save = sync.batch_upsert_guide_airings

        def save(rows):
            progress.append(dict(service.guide_progress or {}))
            real_save(rows)

        with mock.patch.object(sync.tablo_manager, "request_bulk", new=tablo), \
                mock.patch.object(sync, "batch_upsert_guide_airings", side_effect=save):
            asyncio.run(service._sync_guide())

        with db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM guide_airings").fetchone()[0], len(paths))
        batches = [r for r in tablo.requests if r[1] == "/batch"]
        self.assertEqual(len(batches), 7 + 1)  # 320 / 50, plus the refused one again
        self.assertTrue(progress and all(p.get("first") and p.get("total") == len(paths) for p in progress))

    def test_rejected_batches_fall_back_to_smaller_ones(self):
        paths = [f"/guide/airings/{i}" for i in range(12)]
        tablo = FakeTablo(paths, batch_status=404)
        with mock.patch.object(sync.tablo_manager, "request_bulk", new=tablo):
            got = asyncio.run(fetch_objects(paths))
        self.assertEqual(set(got), set(paths))
        self.assertTrue(any(m == "GET" and p.startswith("/guide/airings/") for m, p in tablo.requests))

    def test_airings_no_longer_listed_are_removed(self):
        soon = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.batch_upsert_guide_airings([{"path": p, "air_datetime": soon} for p in ("/a/1", "/a/2")])
        self.assertEqual(db.prune_guide_airings(["/a/1"]), 1)
        with db.get_connection() as conn:
            self.assertEqual([r[0] for r in conn.execute("SELECT path FROM guide_airings")], ["/a/1"])


if __name__ == "__main__":
    unittest.main()
