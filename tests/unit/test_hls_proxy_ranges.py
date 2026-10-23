try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.transcode import StreamSession, transcode_manager

FILE = bytes(range(256)) * 4  # a recording's one file, 1 KB


def tablo(request: httpx.Request) -> httpx.Response:
    """The Tablo: the recording's file, honouring Range like the real one."""
    rng = request.headers.get("range")
    if not rng:
        return httpx.Response(200, content=FILE, headers={"content-type": "video/mp2t"})
    start, end = (int(x) for x in rng.split("=")[1].split("-"))
    return httpx.Response(206, content=FILE[start:end + 1],
                          headers={"content-type": "video/mp2t", "content-range": f"bytes {start}-{end}/{len(FILE)}"})


class HlsProxyRangeTests(unittest.TestCase):
    """VLC links: a recording is one file read in byte ranges, so the proxy must pass Range on (it
    sent the whole file for every piece, and VLC and FFmpeg gave up)."""

    def setUp(self):
        sess = StreamSession("rng123", "http://192.168.1.164:80/stream/pl.m3u8?x")
        transcode_manager.sessions[sess.session_id] = sess
        self.addCleanup(transcode_manager.sessions.pop, sess.session_id, None)
        client = httpx.AsyncClient(transport=httpx.MockTransport(tablo))
        patcher = mock.patch.object(transcode_manager, "_http", client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def test_a_range_is_passed_on(self):
        r = self.client.get("/api/hls/rng123/stream/segw.ts?x", headers={"Range": "bytes=100-199"})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.content, FILE[100:200])
        self.assertEqual(r.headers["content-range"], "bytes 100-199/1024")

    def test_without_a_range_the_whole_file(self):
        r = self.client.get("/api/hls/rng123/stream/segw.ts?x")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.content), len(FILE))


if __name__ == "__main__":
    unittest.main()
