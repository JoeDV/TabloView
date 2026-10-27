import tempfile
import unittest
from pathlib import Path
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
            mock.patch.object(lanauth, "ACTIVITY_FILE", Path(tempfile.mkdtemp()) / "lan_activity.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        lanauth._failures.clear()
        lanauth._seen_written.clear()

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
        # Not as a value anywhere (a substring check failed now and then: the random salt, hash and
        # secret are ~160 hex characters, which contain "2468" about once in 400 runs)
        stored = self.settings["lan_pin"]
        self.assertEqual(set(stored), {"salt", "hash"})
        self.assertNotIn("2468", [v for v in stored.values()] + [str(v) for v in self.settings.values()])
        self.assertEqual(len(stored["hash"]), 128)

    def test_requests_from_another_device_get_401(self):
        lanauth.set_pin("2468")
        client = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))
        r = client.get("/api/shows", headers=HDR)
        self.assertEqual((r.status_code, r.json()["code"]), (401, "pin_required"))
        r = client.post("/api/lan/login", json={"pin": "2468"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client.get("/api/lan/status", headers=HDR).json()["signed_in"], True)
        self.assertEqual(client.post("/api/lan/pin", json={"pin": "1111"}, headers=HDR).status_code, 403)  # only on the PC

    def test_lockouts_double_each_time_up_to_an_hour(self):
        lanauth.set_pin("2468")
        now, waits = 1000.0, []
        for _ in range(8):
            for _ in range(lanauth.MAX_TRIES):
                ok, wait = lanauth.check_pin("0000", "phone", now=now)
            waits.append(wait)
            now += wait + 1
        self.assertEqual(waits, [60, 120, 240, 480, 960, 1920, 3600, 3600])
        # Other addresses aren't affected, and the right PIN starts over
        self.assertEqual(lanauth.check_pin("2468", "tv", now=now), (True, 0))
        self.assertEqual(lanauth.check_pin("2468", "phone", now=now), (True, 0))
        for _ in range(lanauth.MAX_TRIES):
            ok, wait = lanauth.check_pin("0000", "phone", now=now)
        self.assertEqual(wait, 60)

    def test_lockouts_are_short_again_after_a_quiet_day(self):
        lanauth.set_pin("2468")
        now = 1000.0
        for _ in range(2):  # locked out twice: 60 s, then 120 s
            for _ in range(lanauth.MAX_TRIES):
                ok, wait = lanauth.check_pin("0000", "phone", now=now)
            now += wait + 1
        self.assertEqual(wait, 120)
        # A third lockout soon after would be 240 s; a day later it's back to 60 s
        later = now + lanauth.LOCKOUT_FORGET_SECONDS + 1
        for _ in range(lanauth.MAX_TRIES):
            ok, wait = lanauth.check_pin("0000", "phone", now=later)
        self.assertEqual(wait, 60)

    def test_device_names(self):
        app_ua = "Mozilla/5.0 (Linux; Android 12; Google TV Streamer; wv) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36 TabloViewTV/1.0"
        self.assertEqual(lanauth.describe_agent(app_ua), "TabloView TV app")
        self.assertEqual(lanauth.describe_agent("Mozilla/5.0 (Linux; Android 9; AFTMM) AppleWebKit/537.36 Silk/120.1 Chrome/120.0 Safari/537.36"), "Fire TV, Silk")
        self.assertEqual(lanauth.describe_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 Version/18.4 Mobile/15E148 Safari/604.1"), "iPhone, Safari")
        self.assertEqual(lanauth.describe_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0"), "Windows PC, Edge")
        self.assertEqual(lanauth.describe_agent("VLC/3.0.21 LibVLC/3.0.21"), "VLC")
        self.assertEqual(lanauth.describe_agent(None), "Unknown device")

    def test_sign_ins_wrong_pins_and_devices_are_recorded(self):
        lanauth.set_pin("2468")
        phone = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))
        ua = {**HDR, "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) Safari/604.1"}
        self.assertEqual(phone.post("/api/lan/login", json={"pin": "1111"}, headers=ua).status_code, 401)
        self.assertEqual(phone.post("/api/lan/login", json={"pin": "2468"}, headers=ua).status_code, 200)
        a = lanauth.activity()
        self.assertEqual([(e["what"], e["address"], e["device"]) for e in a["events"]],
                         [("signed_in", "192.168.1.20", "iPhone, Safari"), ("wrong_pin", "192.168.1.20", "iPhone, Safari")])
        self.assertEqual(a["wrong_pins_today"], 1)
        self.assertEqual([(d["address"], d["device"]) for d in a["devices"]], [("192.168.1.20", "iPhone, Safari")])
        # Only this PC sees it or clears it
        self.assertEqual(phone.get("/api/lan/activity", headers=ua).status_code, 403)
        pc = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.assertEqual(pc.get("/api/lan/activity", headers=HDR).json()["devices"][0]["device"], "iPhone, Safari")
        self.assertEqual(pc.post("/api/lan/activity/clear", headers=HDR).status_code, 200)
        self.assertEqual(lanauth.activity()["events"], [])

    def test_lockout_is_recorded_with_its_wait(self):
        lanauth.set_pin("2468")
        phone = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.21", 50000))
        for _ in range(lanauth.MAX_TRIES):
            r = phone.post("/api/lan/login", json={"pin": "0000"}, headers=HDR)
        self.assertEqual(r.status_code, 429)
        self.assertIn("60 seconds", r.json()["detail"])
        self.assertEqual(lanauth.activity()["events"][0], {**lanauth.activity()["events"][0], "what": "locked_out", "wait": 60})

    def test_last_use_is_written_every_few_minutes_at_most(self):
        lanauth.note_seen("192.168.1.30", "VLC/3.0", now=1000)
        lanauth.note_seen("192.168.1.30", "VLC/3.0", now=1100)
        self.assertEqual(lanauth.activity()["devices"][0]["last"], 1000)
        lanauth.note_seen("192.168.1.30", "VLC/3.0", now=1000 + lanauth.SEEN_EVERY)
        self.assertEqual(lanauth.activity()["devices"][0]["last"], 1000 + lanauth.SEEN_EVERY)


if __name__ == "__main__":
    unittest.main()
