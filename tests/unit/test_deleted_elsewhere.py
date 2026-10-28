import asyncio
import unittest
from unittest import mock

import httpx

from app import database as db
from app.routes import episodes
from app.tablo_client import tablo_manager


def not_found(path):
    req = httpx.Request("POST", "http://tablo/watch")
    return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))


class DeletedElsewhereTests(unittest.TestCase):
    """Playing a recording deleted from the Tablo by another app since the last sync: taken out of the
    library at once, only when the Tablo also says the recording itself is gone."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.commit()
        db.upsert_episode({"id": "ep_1", "show_id": "ncis", "show_title": "NCIS", "path": "/recordings/series/episodes/1",
                           "season_number": 24, "episode_number": 4, "title": "t", "air_date": "2026-10-20T00:00Z",
                           "duration": 3600, "status": "Unwatched", "position": 1921, "raw_json": {}})

    def play(self, airing_status):
        with mock.patch.object(tablo_manager, "get_airing_watch_url", side_effect=not_found("/watch")), \
             mock.patch.object(tablo_manager, "request_local", return_value=httpx.Response(airing_status)):
            return asyncio.run(episodes.watch_episode("ep_1", request=None))

    def test_gone_from_the_tablo(self):
        with self.assertRaises(episodes.HTTPException) as cm:
            self.play(404)
        self.assertEqual(cm.exception.status_code, 410)
        self.assertIsNone(db.get_episode_by_id("ep_1"))

    def test_still_there_is_kept(self):
        # /watch said not found but the recording is still listed: a Tablo hiccup, not a deletion
        with self.assertRaises(episodes.HTTPException) as cm:
            self.play(200)
        self.assertEqual(cm.exception.status_code, 502)
        self.assertIsNotNone(db.get_episode_by_id("ep_1"))


if __name__ == "__main__":
    unittest.main()
