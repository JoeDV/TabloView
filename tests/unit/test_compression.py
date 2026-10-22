try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest

from fastapi.testclient import TestClient

from app import database as db
from app.main import app


class CompressionTests(unittest.TestCase):
    """Pages, scripts and data are compressed for other devices on the network; video isn't."""

    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def test_the_app_script_is_compressed(self):
        r = self.client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.headers.get("content-encoding"), "gzip")

    def test_video_is_not(self):
        # A missing segment is enough: the response must not be gzipped either way
        r = self.client.get("/api/transcoded/nosuch/00001.ts", headers={"Accept-Encoding": "gzip"})
        self.assertNotEqual(r.headers.get("content-encoding"), "gzip")

    def test_the_database_keeps_a_write_ahead_log(self):
        db.init_db()
        with db.get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")


if __name__ == "__main__":
    unittest.main()
