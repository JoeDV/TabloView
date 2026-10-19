import asyncio
import unittest
from unittest import mock

import httpx

from app import database as db
from app import sync_service as sync
from app.sync_service import LibrarySyncService


def airing(path):
    return {"series_path": "/guide/series/1", "airing_details": {"datetime": "2099-01-01T00:00Z", "duration": 1800, "show_title": "Show"},
            "episode": {"title": path}, "qualifiers": []}


class GuideLoadTests(unittest.TestCase):
    """A first guide load fetches thousands of airings: it reports progress, saves as it goes,
    and waits out the Tablo's break instead of giving up on everything after it."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM guide_airings")
            conn.execute("DELETE FROM sync_meta")
            conn.commit()

    def test_progress_and_waiting_out_a_refusal(self):
        paths = [f"/guide/airings/{i}" for i in range(sync.LARGE_AIRING_FETCH + 50)]
        service = LibrarySyncService()
        seen = {"refused": False, "progress": []}

        async def fake(method, path, body=""):
            if path == "/guide/airings":
                return httpx.Response(200, json=paths)
            if path.startswith("/guide/airings/"):
                if path == paths[150] and not seen["refused"]:
                    seen["refused"] = True
                    raise httpx.ConnectError("All connection attempts failed")
                if service.guide_progress:
                    seen["progress"].append(dict(service.guide_progress))
                return httpx.Response(200, json=airing(path))
            return httpx.Response(200, json=[])  # show catalog lists: nothing

        with mock.patch.object(sync.tablo_manager, "request_bulk", side_effect=fake), \
                mock.patch.object(sync, "TABLO_BREAK_SECONDS", 0), \
                mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            asyncio.run(service._sync_guide())

        with db.get_connection() as conn:
            saved = conn.execute("SELECT COUNT(*) FROM guide_airings").fetchone()[0]
        self.assertEqual(saved, len(paths))  # the refused one was fetched again after the break
        self.assertTrue(all(p["first"] and p["total"] == len(paths) for p in seen["progress"]))
        self.assertGreater(max(p["done"] for p in seen["progress"]), 0)  # progress moved during the load


if __name__ == "__main__":
    unittest.main()
