try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import unittest
from unittest import mock

import httpx

from app.routes import guide


class Tablo:
    """Answers like a Tablo asked to update its guide: the update finishes after a couple of checks."""

    def __init__(self, accept=True):
        self.accept = accept
        self.calls = []
        self.checks = 0

    async def __call__(self, method, path, body=""):
        self.calls.append((method, path))
        if path == "/server/guide/refresh?lh":
            return httpx.Response(200 if self.accept else 500, json={})
        if path == "/server/guide/status?lh":
            self.checks += 1
            done = self.accept and self.checks >= 3
            return httpx.Response(200, json={"guide_seeded": True, "download_progress": None if done or self.checks == 1 else 0.5,
                                             "last_update": "2026-10-22T18:47:42Z" if done else "2026-10-22T12:00:00Z"})
        raise AssertionError(path)


class GuideRefreshTests(unittest.TestCase):
    """Refresh guide asks the Tablo to download a new guide first, as its app's Update guide button does."""

    def run_refresh(self, tablo):
        sync = mock.AsyncMock()
        with mock.patch.object(guide.tablo_manager, "request_local", new=tablo), \
             mock.patch.object(guide.sync_service, "sync_guide", new=sync), \
             mock.patch.object(guide, "GUIDE_STATUS_EVERY", 0):
            asyncio.run(guide.refresh_guide_from_tablo())
        return sync

    def test_the_tablo_updates_then_tabloview_reads_it(self):
        tablo = Tablo()
        sync = self.run_refresh(tablo)
        self.assertIn(("POST", "/server/guide/refresh?lh"), tablo.calls)
        self.assertEqual(tablo.checks, 3)  # before, while downloading, done
        sync.assert_awaited_once()
        self.assertEqual(guide.guide_refresh["stage"], "done")

    def test_a_refused_update_still_reads_what_the_tablo_has(self):
        tablo = Tablo(accept=False)
        sync = self.run_refresh(tablo)
        self.assertEqual(tablo.checks, 1)  # no waiting
        sync.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
