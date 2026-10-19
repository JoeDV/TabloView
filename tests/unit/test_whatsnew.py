try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app import whatsnew
from app.config import APP_VERSION



class WhatsNewTests(unittest.TestCase):
    def setUp(self):
        self.settings = {"last_seen_version": None}
        patches = [
            mock.patch.object(whatsnew, "load_settings", side_effect=lambda: dict(self.settings)),
            mock.patch.object(whatsnew, "save_settings", side_effect=lambda u: self.settings.update(u)),
            mock.patch.dict(whatsnew.NOTES, {APP_VERSION: ["Something new"]}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_fresh_install_does_not_show_notes(self):
        with mock.patch.object(whatsnew, "get_sync_meta", return_value=None):
            whatsnew.init()
        self.assertFalse(whatsnew.pending()["show"])

    def test_upgrade_shows_notes_once(self):
        with mock.patch.object(whatsnew, "get_sync_meta", return_value="2026-10-17T00:00:00+00:00"):
            whatsnew.init()
        self.assertTrue(whatsnew.pending()["show"])
        whatsnew.mark_seen()
        self.assertFalse(whatsnew.pending()["show"])

    def test_older_seen_version_shows_notes(self):
        self.settings["last_seen_version"] = "1.0.0"
        self.assertEqual(whatsnew.pending()["notes"], ["Something new"])


if __name__ == "__main__":
    unittest.main()
