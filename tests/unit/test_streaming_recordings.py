try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import unittest
from unittest import mock

import httpx

from app.tablo_client import tablo_manager


class Tablo:
    """Recordings of streaming channels exist only for requests ending in ?lh (as on a real Tablo,
    2026-10-21); antenna recordings answer either way."""

    def __init__(self, streaming_paths):
        self.streaming = set(streaming_paths)
        self.calls = []

    async def __call__(self, method, path, body=""):
        self.calls.append((method, path))
        req = httpx.Request(method, "http://tablo:8887" + path)
        bare = path.split("?")[0].removesuffix("/watch")
        if bare in self.streaming and not path.endswith("?lh"):
            return httpx.Response(404, json={"error": {"code": "object_not_found"}}, request=req)
        if bare == "/recordings/series/episodes/gone":
            return httpx.Response(404, json={"error": {"code": "object_not_found"}}, request=req)
        if path.split("?")[0].endswith("/watch"):
            return httpx.Response(200, json={"playlist_url": "http://tablo/pl.m3u8", "token": "t"}, request=req)
        return httpx.Response(200, json={}, request=req)


class StreamingRecordingTests(unittest.TestCase):
    def run_with(self, tablo, coro):
        with mock.patch.object(tablo_manager, "request_local", new=tablo), \
             mock.patch.object(tablo_manager, "device", mock.Mock(client_id="c")):
            return asyncio.run(coro)

    def test_streaming_recordings_are_asked_again_with_lh(self):
        tablo = Tablo({"/recordings/series/episodes/346002"})
        r = self.run_with(tablo, tablo_manager.request_recording("PATCH", "/recordings/series/episodes/346002", "{}"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(tablo.calls, [("PATCH", "/recordings/series/episodes/346002"),
                                       ("PATCH", "/recordings/series/episodes/346002?lh")])

    def test_antenna_recordings_are_asked_as_before(self):
        tablo = Tablo(set())
        self.run_with(tablo, tablo_manager.request_recording("PATCH", "/recordings/series/episodes/1", "{}"))
        self.assertEqual(tablo.calls, [("PATCH", "/recordings/series/episodes/1")])

    def test_a_streaming_recording_plays(self):
        tablo = Tablo({"/recordings/series/episodes/346002"})
        w = self.run_with(tablo, tablo_manager.get_airing_watch_url("/recordings/series/episodes/346002"))
        self.assertEqual(w["playlist_url"], "http://tablo/pl.m3u8")

    def test_deleting_a_streaming_recording_really_deletes_it(self):
        # A plain DELETE says "not found", which used to count as "already gone"
        tablo = Tablo({"/recordings/series/episodes/346002"})
        self.assertTrue(self.run_with(tablo, tablo_manager.delete_airing("/recordings/series/episodes/346002")))
        self.assertIn(("DELETE", "/recordings/series/episodes/346002?lh"), tablo.calls)

    def test_gone_means_not_found_either_way(self):
        tablo = Tablo(set())
        self.assertTrue(self.run_with(tablo, tablo_manager.delete_airing("/recordings/series/episodes/gone")))
        self.assertEqual(len(tablo.calls), 2)


if __name__ == "__main__":
    unittest.main()
