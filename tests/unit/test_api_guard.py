"""Runs the real FastAPI app in-process (against the throwaway data folder, not signed in to any Tablo)
and checks the request guard, path-traversal protection and a few endpoints."""
try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock
from fastapi.testclient import TestClient

from app.main import app
from app.tablo_client import tablo_manager

HDR = {"X-TabloView": "1"}



class ApiGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, base_url="http://127.0.0.1:7070")
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
