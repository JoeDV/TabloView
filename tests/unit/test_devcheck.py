try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest

from fastapi.testclient import TestClient

from app import database as db
from app.main import app

HDR = {"X-TabloView": "1"}


class DevCheckTests(unittest.TestCase):
    """POST /api/dev/check: would the server take this request? Validated, never run. The browser
    tests' faked saves ask it, so a save the server would refuse fails the test run."""

    def setUp(self):
        db.init_db()
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def check(self, method, url, body=None):
        r = self.client.post("/api/dev/check", json={"method": method, "url": url, "body": body}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_refused_like_the_server_would(self):
        r = self.check("POST", "/api/settings", '{"home_hidden": ["nope"]}')
        self.assertFalse(r["ok"])
        self.assertEqual(r["detail"][0]["loc"], ["body", "home_hidden", 0])
        self.assertFalse(self.check("POST", "/api/guide/alerts", '{"word": 5}')["ok"])
        self.assertFalse(self.check("POST", "/api/shows/keep", '{"count": 3}')["ok"])          # show_id missing
        self.assertFalse(self.check("POST", "/api/shows/keep?show_id=x", '{"count": "lots"}')["ok"])
        self.assertFalse(self.check("POST", "/api/settings", "{not json")["ok"])

    def test_good_ones_pass(self):
        self.assertTrue(self.check("POST", "/api/settings", '{"home_hidden": ["onnow"]}')["ok"])
        self.assertTrue(self.check("POST", "/api/shows/keep?show_id=x", '{"count": 3}')["ok"])
        self.assertTrue(self.check("POST", "http://127.0.0.1:7070/api/guide/alerts", '{"word": "Eagles"}')["ok"])

    def test_nothing_is_run(self):
        before = self.client.get("/api/guide/alerts", headers=HDR).json()["words"]
        self.assertTrue(self.check("POST", "/api/guide/alerts", '{"word": "Checked only"}')["ok"])
        self.assertEqual(self.client.get("/api/guide/alerts", headers=HDR).json()["words"], before)

    def test_no_such_route(self):
        r = self.check("POST", "/api/nowhere", "{}")
        self.assertEqual((r["ok"], r["status"]), (False, 404))


if __name__ == "__main__":
    unittest.main()
