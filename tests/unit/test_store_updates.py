import asyncio
import unittest
from unittest import mock

from app import updates


class StoreUpdateTests(unittest.TestCase):
    """Store copies ask the Microsoft Store whether there's a newer version (the Store installs it)."""

    def setUp(self):
        updates._cache.update(checked=0.0, result=None)
        p = mock.patch.object(updates, "IS_STORE", True)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(updates._cache.update, checked=0.0, result=None)

    def check(self):
        return asyncio.run(updates.check_for_update(force=True))

    def test_newer_version_in_the_store(self):
        with mock.patch.object(updates, "store_update_version", new=mock.AsyncMock(return_value="9.9.9")):
            u = self.check()
        self.assertTrue(u["update_available"] and u["store"])
        self.assertEqual((u["latest"], u["download_url"]), ("9.9.9", updates.STORE_LINK))

    def test_up_to_date(self):
        with mock.patch.object(updates, "store_update_version", new=mock.AsyncMock(return_value=None)):
            u = self.check()
        self.assertFalse(u["update_available"])
        self.assertIsNone(u["error"])

    def test_store_unavailable_is_reported_not_raised(self):
        with mock.patch.object(updates, "store_update_version", new=mock.AsyncMock(side_effect=OSError("no store"))):
            u = self.check()
        self.assertFalse(u["update_available"])
        self.assertIn("Microsoft Store", u["error"])
        # Says what to do, not Windows' own error text (a user got a "WinNT" message)
        self.assertIn("Get updates", u["error"])
        self.assertNotIn("no store", u["error"])


if __name__ == "__main__":
    unittest.main()
