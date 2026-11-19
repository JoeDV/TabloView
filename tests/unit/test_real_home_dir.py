import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import config


class RealHomeDirTests(unittest.TestCase):
    """Settings → About shows where the app data really is: a Store copy's AppData\\Local\\TabloView is
    redirected by Windows into the package's LocalCache (a forum user couldn't find settings.json)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.local = Path(tmp.name)
        self.home = self.local / "TabloView"
        self.redirected = self.local / "Packages" / "Fam_123" / "LocalCache" / "Local" / "TabloView"
        env = {k: v for k, v in os.environ.items() if k != "TABLOVIEW_HOME"}
        for p in (mock.patch.object(config, "_local", self.local, create=True),
                  mock.patch.object(config, "HOME_DIR", self.home),
                  mock.patch.object(config, "STORE_PACKAGE", "Fam_123"),
                  mock.patch.object(config, "IS_PACKAGED", True),
                  mock.patch.dict(os.environ, env, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def test_store_copy_shows_the_package_folder(self):
        self.redirected.mkdir(parents=True)
        with mock.patch.object(config, "IS_STORE", True):
            self.assertEqual(config.real_home_dir(), self.redirected)

    def test_store_copy_without_that_folder_shows_the_usual_one(self):
        with mock.patch.object(config, "IS_STORE", True):
            self.assertEqual(config.real_home_dir(), self.home)

    def test_installer_copy_shows_the_usual_one(self):
        self.redirected.mkdir(parents=True)
        with mock.patch.object(config, "IS_STORE", False):
            self.assertEqual(config.real_home_dir(), self.home)


if __name__ == "__main__":
    unittest.main()
