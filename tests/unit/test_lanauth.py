import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import lanauth
from app.main import app

HDR = {"X-TabloView": "1"}


class LanPinTests(unittest.TestCase):
    """Other devices on the network need the PIN; this PC never does."""

    def setUp(self):
        self.settings = {}
        patches = [
            mock.patch.object(lanauth, "load_settings", side_effect=lambda: dict(self.settings)),
            mock.patch.object(lanauth, "save_settings", side_effect=lambda u: self.settings.update(u)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        lanauth._failures.clear()

    def test_this_pc_and_pages_are_never_blocked(self):
        self.assertIsNone(lanauth.blocked("/api/shows", "127.0.0.1", None))
        self.assertIsNone(lanauth.blocked("/api/shows", "::1", None))
        self.assertIsNone(lanauth.blocked("/static/app.js", "192.168.1.20", None))
        self.assertIsNone(lanauth.blocked("/api/lan/login", "192.168.1.20", None))

    def test_other_devices_need_a_pin_set_then_signed_in(self):
        self.assertEqual(lanauth.blocked("/api/shows", "192.168.1.20", None), "pin_not_set")
        lanauth.set_pin("2468")
        self.assertEqual(lanauth.blocked("/api/shows", "192.168.1.20", None), "pin_required")
        self.assertEqual(lanauth.blocked("/downloads/x.mp4", "192.168.1.20", "junk"), "pin_required")
        self.assertIsNone(lanauth.blocked("/api/shows", "192.168.1.20", lanauth.make_token()))

    def test_changing_the_pin_or_signing_out_ends_remembered_devices(self):
        lanauth.set_pin("2468")
        token = lanauth.make_token()
        lanauth.sign_out_all()
        self.assertFalse(lanauth.token_ok(token))
        token = lanauth.make_token()
        lanauth.set_pin("1357")
        self.assertFalse(lanauth.token_ok(token))

    def test_remembered_for_90_days(self):
        lanauth.set_pin("2468")
        token = lanauth.make_token(now=1000)
        self.assertTrue(lanauth.token_ok(token, now=1000 + 89 * 86400))
        self.assertFalse(lanauth.token_ok(token, now=1000 + 91 * 86400))

    def test_wrong_pins_lock_out_for_a_minute(self):
        lanauth.set_pin("2468")
        for _ in range(lanauth.MAX_TRIES - 1):
            self.assertEqual(lanauth.check_pin("0000", "phone", now=100), (False, 0))
        self.assertEqual(lanauth.check_pin("0000", "phone", now=100), (False, lanauth.LOCKOUT_SECONDS))
        self.assertFalse(lanauth.check_pin("2468", "phone", now=110)[0])  # still locked, even with the right PIN
        self.assertEqual(lanauth.check_pin("2468", "phone", now=100 + lanauth.LOCKOUT_SECONDS + 1), (True, 0))

    def test_pin_is_stored_hashed(self):
        lanauth.set_pin("2468")
        self.assertNotIn("2468", str(self.settings))

    def test_requests_from_another_device_get_401(self):
        lanauth.set_pin("2468")
        client = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))
        r = client.get("/api/shows", headers=HDR)
        self.assertEqual((r.status_code, r.json()["code"]), (401, "pin_required"))
        r = client.post("/api/lan/login", json={"pin": "2468"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client.get("/api/lan/status", headers=HDR).json()["signed_in"], True)
        self.assertEqual(client.post("/api/lan/pin", json={"pin": "1111"}, headers=HDR).status_code, 403)  # only on the PC


if __name__ == "__main__":
    unittest.main()
