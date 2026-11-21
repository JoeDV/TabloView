try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import database as db
from app import lanauth, tuner
from app.main import app

HDR = {"X-TabloView": "1"}


class ThisPcOnlyTests(unittest.TestCase):
    """A device elsewhere at home, signed in with the PIN, can't restore or save a backup (its
    settings include ones only this PC may change, such as who skips the PIN over Tailscale), or
    change the Claude key or Start with Windows."""

    def setUp(self):
        db.init_db()
        # Past the PIN check, but not this PC
        p = mock.patch.object(lanauth, "blocked", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        self.remote = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))

    def test_refused_from_another_device(self):
        for path, body in (("/api/backup/restore", {"kind": "TabloView backup", "settings": {"tailscale_no_pin": True}}),
                           ("/api/backup", {}),
                           ("/api/settings/claude_key", {"key": None}),
                           ("/api/system/startup", {"enabled": True})):
            r = self.remote.post(path, json=body, headers=HDR)
            self.assertEqual(r.status_code, 403, path)
            self.assertIn("only be changed on the PC", r.json()["detail"])

    def test_this_pc_can_still_save_a_backup(self):
        local = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        r = local.post("/api/backup", json={"browser": {}}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertIn("backup", r.json())


class TunerOtherWebsitesTests(unittest.TestCase):
    """The tuner (port 5004) turns away requests a page on another website makes from a browser here;
    Plex, Jellyfin and the other apps send no Sec-Fetch-Site and are unaffected."""

    def setUp(self):
        p = mock.patch.object(tuner, "device_id", return_value="1A2B3C4D")
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(tuner.app, base_url="http://127.0.0.1:5004", client=("127.0.0.1", 50000))

    def test_other_websites_refused(self):
        for site in ("cross-site", "same-site"):
            r = self.client.get("/discover.json", headers={"Sec-Fetch-Site": site})
            self.assertEqual(r.status_code, 403, site)

    def test_apps_and_typed_addresses_still_work(self):
        self.assertEqual(self.client.get("/discover.json").status_code, 200)
        self.assertEqual(self.client.get("/discover.json", headers={"Sec-Fetch-Site": "none"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
