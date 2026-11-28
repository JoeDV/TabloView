try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import lanauth
from app.main import app


class TvAppDownloadTests(unittest.TestCase):
    """The TV app at /app, fetched by Downloader on a Fire TV or Google TV: no PIN, and HEAD answered
    (Downloader asks that first; a 405 sent it back to the address screen)."""

    def fetch(self, method):
        client = TestClient(app, base_url="http://192.168.1.69:7070", client=("192.168.1.77", 50000))
        with mock.patch.object(lanauth, "network_access_on", return_value=True),              mock.patch.object(lanauth, "pin_set", return_value=True):
            return client.request(method, "/app", follow_redirects=False)

    def test_head_is_answered_like_get(self):
        get, head = self.fetch("GET"), self.fetch("HEAD")
        self.assertIn(get.status_code, (200, 307))
        self.assertEqual(head.status_code, get.status_code)
        if get.status_code == 200:
            self.assertEqual(head.headers["content-type"], "application/vnd.android.package-archive")
            self.assertEqual(head.headers["content-length"], get.headers["content-length"])
            self.assertEqual(head.content, b"")
            # Sent as it is, never compressed: a downloader that saves what it's sent got a broken app
            self.assertNotIn("content-encoding", get.headers)
            self.assertEqual(len(get.content), int(get.headers["content-length"]))
        else:  # (no copy here: GitHub's)
            self.assertEqual(head.headers["location"], get.headers["location"])


if __name__ == "__main__":
    unittest.main()
