try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import transcode
from app.main import app
from app.transcode import StreamSession, transcode_manager

HDR = {"X-TabloView": "1"}


class AbandonedStreamTests(unittest.TestCase):
    """A stream no page uses any more is closed. A TV browser switched off never said goodbye, and
    its stream stayed open until TabloView restarted (commercial finding said "paused" all along)."""

    def setUp(self):
        self.sess = StreamSession("abc123", "http://192.168.1.164:8887/stream/pl.m3u8")
        transcode_manager.sessions[self.sess.session_id] = self.sess
        self.addCleanup(transcode_manager.sessions.pop, self.sess.session_id, None)
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def close_after(self, idle_seconds):
        self.sess.last_used = time.time() - idle_seconds
        with mock.patch.object(transcode_manager, "stop_session") as stop:
            transcode_manager.close_abandoned()
        return stop

    def test_unused_for_ten_minutes_is_closed(self):
        self.close_after(transcode.ABANDONED_SECONDS + 5).assert_called_once_with("abc123")

    def test_a_paused_player_isnt(self):
        self.close_after(transcode.ABANDONED_SECONDS - 60).assert_not_called()

    def test_the_players_check_in_keeps_it(self):
        self.sess.last_used = 0
        r = self.client.post("/api/live/alive", headers=HDR, json={"session_ids": ["abc123", "gone1"]})
        self.assertEqual(r.json(), {"gone": ["gone1"]})
        self.assertGreater(self.sess.last_used, time.time() - 5)

    def test_fetching_video_keeps_it(self):
        self.sess.last_used = 0
        self.client.get("/api/transcoded/abc123/playlist.m3u8")  # 404s here (no files); still counts
        self.assertGreater(self.sess.last_used, time.time() - 5)


if __name__ == "__main__":
    unittest.main()
