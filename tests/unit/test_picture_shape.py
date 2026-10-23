try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest

from fastapi.testclient import TestClient

from app import database as db
from app.main import app
from app.settings import load_settings, save_settings

HDR = {"X-TabloView": "1"}


class PictureShapeTests(unittest.TestCase):
    """The player's picture shape is kept per channel, for diginets that send the wrong shape."""

    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        save_settings({"picture_shapes": {}})

    def shape(self, channel, shape):
        return self.client.post("/api/settings/picture_shape", headers=HDR, json={"channel": channel, "shape": shape})

    def test_a_shape_is_kept_for_that_channel(self):
        self.shape("S19593_013_02", "4:3")
        r = self.shape("S10991_008_03", "zoom")
        self.assertEqual(r.json()["picture_shapes"], {"S19593_013_02": "4:3", "S10991_008_03": "zoom"})
        self.assertEqual(self.client.get("/api/settings").json()["picture_shapes"]["S19593_013_02"], "4:3")

    def test_auto_forgets_it(self):
        self.shape("S19593_013_02", "16:9")
        self.shape("S19593_013_02", "auto")
        self.assertEqual(load_settings()["picture_shapes"], {})

    def test_the_list_has_a_limit(self):
        save_settings({"picture_shapes": {f"S{i}": "4:3" for i in range(500)}})
        self.assertEqual(self.shape("S_new", "zoom").status_code, 400)
        self.assertEqual(self.shape("S1", "zoom").status_code, 200)  # changing one already there is fine

    def test_only_known_shapes(self):
        self.assertEqual(self.shape("S19593_013_02", "21:9").status_code, 422)

    def test_a_recording_knows_its_channel(self):
        # The same identifier live TV uses, so a shape chosen while watching live applies to recordings
        raw = {"airing_details": {"channel": {"channel": {"call_sign": "WTHR", "channel_identifier": "S19593_013_01"}}}}
        self.assertEqual(db.recording_details(raw)["channel_identifier"], "S19593_013_01")
        self.assertIsNone(db.recording_details({})["channel_identifier"])


class SettingsPrivacyTests(unittest.TestCase):
    """Settings sent to the page never include the PIN's hash or the secret that signs devices in."""

    def test_settings_leave_out_the_pin_and_secret(self):
        save_settings({"lan_pin": {"salt": "aa", "hash": "bb"}, "lan_secret": "cc"})
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        try:
            for body in (client.get("/api/settings").json(),
                         client.post("/api/settings", headers=HDR, json={"notifications": True}).json()):
                self.assertNotIn("lan_pin", body)
                self.assertNotIn("lan_secret", body)
        finally:
            save_settings({"lan_pin": None, "lan_secret": None})


if __name__ == "__main__":
    unittest.main()
