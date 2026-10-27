try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import settings


class SettingsFileTests(unittest.TestCase):
    """settings.json is saved in one step with the last good copy kept, so a damaged file doesn't
    lose the PIN and everything else (they used to be replaced by the defaults on the next save)."""

    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.file, self.backup = folder / "settings.json", folder / "settings.bak.json"
        for p in (mock.patch.object(settings, "SETTINGS_FILE", self.file),
                  mock.patch.object(settings, "BACKUP_FILE", self.backup)):
            p.start()
            self.addCleanup(p.stop)

    def test_saves_and_keeps_the_previous_copy(self):
        settings.save_settings({"port": 7071})
        settings.save_settings({"notifications": False})
        self.assertEqual((settings.load_settings()["port"], settings.load_settings()["notifications"]), (7071, False))
        self.assertIn('"port": 7071', self.backup.read_text())
        self.assertFalse(self.file.with_name("settings.json.tmp").exists())

    def test_a_damaged_file_is_read_from_the_copy_and_the_next_save_keeps_everything(self):
        settings.save_settings({"lan_pin": {"salt": "aa", "hash": "bb"}, "port": 7071})
        settings.save_settings({"notifications": False})
        self.file.write_text('{"lan_pin": {"salt": "a', encoding="utf-8")  # cut off mid-write
        self.assertEqual(settings.load_settings()["lan_pin"], {"salt": "aa", "hash": "bb"})
        settings.save_settings({"auto_sync_minutes": 30})
        saved = settings.load_settings()
        self.assertEqual((saved["lan_pin"], saved["port"], saved["auto_sync_minutes"]), ({"salt": "aa", "hash": "bb"}, 7071, 30))
        # The damaged file never became the backup
        self.assertIn("lan_pin", self.backup.read_text())

    def test_no_file_is_the_defaults(self):
        self.assertEqual(settings.load_settings(), settings.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
