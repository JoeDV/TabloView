"""Runs the real FastAPI app in-process (against the throwaway data folder, not signed in to any Tablo)
and checks the request guard, path-traversal protection and a few endpoints."""
try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import tempfile
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from app.main import app
from app.tablo_client import tablo_manager

HDR = {"X-TabloView": "1"}



class ApiGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # As this PC itself (other devices on the network need the PIN; see test_lanauth)
        cls.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_page_and_info_load(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        info = self.client.get("/api/system/info").json()
        self.assertEqual(info["app"], "TabloView")
        self.assertFalse(info["packaged"])

    def test_change_requests_need_the_header(self):
        self.assertEqual(self.client.post("/api/settings", json={"auto_sync_minutes": 30}).status_code, 403)
        r = self.client.post("/api/settings", json={"auto_sync_minutes": 30}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["auto_sync_minutes"], 30)

    def test_foreign_host_is_rejected(self):
        # A DNS-rebinding page reaches the server under a foreign name
        self.assertEqual(self.client.get("/api/system/info", headers={"Host": "evil.example.com"}).status_code, 403)
        for ok_host in ("localhost:7070", "192.168.1.50:7070", "[::1]:7070"):
            self.assertEqual(self.client.get("/api/system/info", headers={"Host": ok_host}).status_code, 200, ok_host)

    def test_this_pcs_tailscale_name_is_accepted(self):
        # Away from home over Tailscale: its full name for this PC, not anyone else's ts.net name
        import app.main as m
        with mock.patch.object(m, "_PC_NAME", "hplaptop"),                 mock.patch.object(m, "_tailscale_name", return_value="hplaptop-1.tailc0c2e.ts.net"):
            for ok in ("hplaptop.tailc0c2e.ts.net:7070", "HPLaptop-1.tailc0c2e.ts.net:7070"):
                self.assertEqual(self.client.get("/api/system/info", headers={"Host": ok}).status_code, 200, ok)
            for bad in ("other.tailc0c2e.ts.net:7070", "hplaptop.evil.example.com:7070", "hplaptop.ts.net:7070",
                        "hplaptop.a.b.ts.net:7070", "hplaptop.tailc0c2e.ts.net.evil.com:7070"):
                self.assertEqual(self.client.get("/api/system/info", headers={"Host": bad}).status_code, 403, bad)

    def test_tv_app_download(self):
        # Another device (a TV, not signed in) gets the TV app at /app; without a bundled copy, GitHub's
        import app.main as m
        tv = TestClient(app, base_url="http://192.168.1.160:7070", client=("192.168.1.92", 50000))
        with mock.patch.object(m, "RESOURCE_DIR", m.Path("nowhere")), mock.patch.object(m, "BASE_DIR", m.Path("nowhere")):
            r = tv.get("/app", follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertEqual(r.headers["location"], m.TV_APP_LATEST)
        with tempfile.TemporaryDirectory() as d:
            (m.Path(d) / "tvapp").mkdir()
            (m.Path(d) / "tvapp" / "TabloView-TV.apk").write_bytes(b"PK apk")
            with mock.patch.object(m, "RESOURCE_DIR", m.Path(d)):
                r = tv.get("/app")
        self.assertEqual((r.status_code, r.content), (200, b"PK apk"))
        self.assertEqual(r.headers["content-type"], "application/vnd.android.package-archive")

    def test_other_websites_cannot_make_reads(self):
        # e.g. <img src="http://127.0.0.1:7070/api/live/vlc/..."> on another site would tune a channel
        for site in ("cross-site", "same-site"):
            r = self.client.get("/api/system/info", headers={"Sec-Fetch-Site": site})
            self.assertEqual(r.status_code, 403, site)
        # TabloView's own pages, typed addresses, and VLC (no header)
        for headers in ({"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {}):
            self.assertEqual(self.client.get("/api/system/info", headers=headers).status_code, 200, headers)
        # The page itself still opens from a link on another site
        self.assertEqual(self.client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 200)

    def test_path_traversal_is_blocked(self):
        for url in ("/downloads/..%2F.env", "/api/transcoded/x/..%2F..%2F.env", "/api/images/..%2F..%2F.env"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_invalid_setting_rejected(self):
        self.assertEqual(self.client.post("/api/settings", json={"auto_sync_minutes": -5}, headers=HDR).status_code, 422)

    def test_signed_out_status(self):
        with mock.patch.object(tablo_manager, "device", None):
            s = self.client.get("/api/auth/status").json()
            self.assertFalse(s["authenticated"])
            self.assertIsNone(s["auth_problem"])


if __name__ == "__main__":
    unittest.main()
