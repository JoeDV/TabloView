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

    def test_every_key_the_app_saves_is_kept(self):
        # save_settings keeps only the keys it knows: commercial_redo was missing, so "Find again" and
        # "Find commercials with Claude" on a recording already done were dropped without a word
        import re
        app = Path(settings.__file__).parent
        saved = set()
        for f in app.rglob("*.py"):
            for call in re.findall(r"save_settings\(\{([^}]*)\}", f.read_text(encoding="utf-8")):
                saved |= set(re.findall(r'"([a-z_0-9]+)":', call))
        self.assertTrue(saved)
        nested = {"salt", "hash"}  # inside lan_pin's value, not keys of their own
        self.assertEqual(sorted(saved - set(settings.DEFAULTS) - nested), [])
        settings.save_settings({"commercial_redo": ["ep_1"]})
        self.assertEqual(settings.load_settings()["commercial_redo"], ["ep_1"])

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
