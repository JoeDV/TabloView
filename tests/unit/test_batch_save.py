try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app import database as db


class BatchSaveTests(unittest.TestCase):
    """Syncs save their shows and recordings in one transaction (one commit, off the main loop)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for t in ("shows", "episodes", "guide_shows", "cloud_art"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def test_library_in_one_commit(self):
        shows = [{"id": f"s{i}", "title": f"Show {i}", "episode_count": 1} for i in range(3)]
        eps = [{"id": f"e{i}", "path": f"/r/{i}", "show_id": f"s{i}", "show_title": f"Show {i}"} for i in range(3)]
        commits = []
        real = db.get_connection

        def counting():
            conn = real()
            return mock.Mock(wraps=conn, __enter__=lambda s: s, __exit__=lambda s, *a: conn.close(),
                             commit=lambda: commits.append(1) or conn.commit(),
                             execute=conn.execute)
        with mock.patch.object(db, "get_connection", side_effect=counting):
            db.save_library(shows, eps)
        self.assertEqual(len(commits), 1)
        self.assertEqual(sorted(s["id"] for s in db.get_shows()), ["s0", "s1", "s2"])
        with db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0], 3)

    def test_guide_batch_keeps_the_cloud_artwork(self):
        db.save_cloud_art({"ID1": {"cover_url": "https://cdn/c.jpg", "backdrop_url": None}})
        db.save_guide_shows([{"path": "/guide/series/1", "title": "A", "cover_url": "/api/images/1",
                              "raw_json": {"identifier": "ID1"}},
                             {"path": "/guide/series/2", "title": "B", "cover_url": "/api/images/2",
                              "raw_json": {"identifier": "ID2"}}])
        with db.get_connection() as conn:
            got = dict(conn.execute("SELECT path, cover_url FROM guide_shows").fetchall())
        self.assertEqual(got, {"/guide/series/1": "https://cdn/c.jpg", "/guide/series/2": "/api/images/2"})

    def test_single_saves_still_work(self):
        db.upsert_show({"id": "solo", "title": "Solo", "episode_count": 1})
        self.assertEqual([s["id"] for s in db.get_shows()], ["solo"])


if __name__ == "__main__":
    unittest.main()
