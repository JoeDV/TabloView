try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import time
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from tablo_api.models import TabloDevice

from app import lanauth
from app.config import TRANSCODE_DIR
from app.main import app
from app.tablo_client import tablo_manager
from app.transcode import VIEWER_GONE_SECONDS, transcode_manager

DEVICE = TabloDevice(
    sid="SID_SHARE",
    name="ShareTablo",
    local_url="http://192.168.1.50:8887",
    lighthouse_token="lh-share",
    account_token="acct-share",
    client_id="client-share",
)
HDR = {"X-TabloView": "1"}


class TunerSharingTests(unittest.TestCase):
    def tearDown(self):
        for sid in list(transcode_manager.sessions.keys()):
            transcode_manager.stop_session(sid, force=True)

    def _make_active_live(self, channel_id="CH_6_1", away=False, captions=True):
        sess = transcode_manager.create_session("http://192.168.1.50/live.m3u8")
        sess.channel_id = channel_id
        sess.tablo_token = "tok-shared-1"
        sess.transcoded = True
        sess.live = True
        sess.away = away
        sess.captions = captions
        sess.proc = SimpleNamespace(poll=lambda: None, kill=mock.Mock(), wait=mock.Mock())
        d = TRANSCODE_DIR / sess.session_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "playlist.m3u8").write_text("#EXTM3U\n00000.ts\n", encoding="utf-8")
        self.first = transcode_manager.add_viewer(sess)  # (the viewer who tuned it)
        return sess

    def test_second_viewer_reuses_active_live_session_without_retuning(self):
        sess = self._make_active_live("CH_6_1")
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch("app.routes.live.TabloClient") as tc_cls:
            r = client.post(
                "/api/live/tune",
                json={"channel_id": "CH_6_1", "transcode": True, "kind": "ota", "captions": False},
                headers=HDR,
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["shared"])
        self.assertEqual(body["session_id"], sess.session_id)
        self.assertEqual(len(sess.viewers), 2)
        self.assertIn(body["viewer"], sess.viewers)
        tc_cls.return_value.watch.assert_not_called()

    def test_first_viewer_stopping_keeps_stream_alive_until_last_viewer_leaves(self):
        sess = self._make_active_live("CH_6_1")
        found = transcode_manager.find_live_session("CH_6_1")
        self.assertIs(found, sess)
        second = transcode_manager.add_viewer(found)

        # Viewer 1 stops: FFmpeg stays alive
        transcode_manager.stop_session(sess.session_id, viewer=self.first)
        self.assertIn(sess.session_id, transcode_manager.sessions)
        self.assertEqual(list(sess.viewers), [second])
        sess.proc.kill.assert_not_called()

        # Viewer 2 stops: FFmpeg is killed and session removed
        transcode_manager.stop_session(sess.session_id, viewer=second)
        self.assertNotIn(sess.session_id, transcode_manager.sessions)
        sess.proc.kill.assert_called_once()

    def test_a_viewer_stopping_twice_doesnt_cut_off_the_other(self):
        sess = self._make_active_live("CH_6_1")
        transcode_manager.add_viewer(sess)
        transcode_manager.stop_session(sess.session_id, viewer=self.first)
        transcode_manager.stop_session(sess.session_id, viewer=self.first)
        self.assertIn(sess.session_id, transcode_manager.sessions)
        sess.proc.kill.assert_not_called()

    def test_a_stop_without_a_viewer_id_ends_one_share(self):
        # (a page loaded before viewer ids: the viewer seen least recently leaves)
        sess = self._make_active_live("CH_6_1")
        second = transcode_manager.add_viewer(sess)
        sess.viewers[self.first] = time.time() - 30
        transcode_manager.stop_session(sess.session_id)
        self.assertEqual(list(sess.viewers), [second])
        transcode_manager.stop_session(sess.session_id)
        self.assertNotIn(sess.session_id, transcode_manager.sessions)

    def test_a_viewer_gone_quiet_is_dropped_and_the_last_one_closes_it(self):
        sess = self._make_active_live("CH_6_1")
        second = transcode_manager.add_viewer(sess)
        now = time.time()
        sess.viewers[self.first] = now - VIEWER_GONE_SECONDS - 5  # a TV app that crashed
        transcode_manager.close_abandoned(now)
        self.assertEqual(list(sess.viewers), [second])
        sess.proc.kill.assert_not_called()
        # Then the other goes quiet too, and no video is fetched: closed, tuner freed (not 10 minutes later)
        sess.viewers[second] = now - VIEWER_GONE_SECONDS - 5
        sess.last_used = now - VIEWER_GONE_SECONDS - 5
        self.assertEqual(transcode_manager.close_abandoned(now), [sess.session_id])
        sess.proc.kill.assert_called_once()

    def test_quiet_viewers_but_video_still_fetched_keep_the_stream(self):
        # (a browser tab slowing its timers in the background, still playing)
        sess = self._make_active_live("CH_6_1")
        now = time.time()
        sess.viewers[self.first] = now - VIEWER_GONE_SECONDS - 5
        sess.last_used = now
        self.assertEqual(transcode_manager.close_abandoned(now), [])
        self.assertIn(sess.session_id, transcode_manager.sessions)

    def test_check_ins_keep_each_viewer(self):
        sess = self._make_active_live("CH_6_1")
        sess.viewers[self.first] = 0
        self.assertTrue(transcode_manager.touch(sess.session_id, self.first))
        self.assertGreater(sess.viewers[self.first], 0)
        self.assertFalse(transcode_manager.touch(sess.session_id, "someone-dropped"))
        self.assertFalse(transcode_manager.touch("no-such-session", self.first))

    def test_streams_nobody_shares_stop_as_before(self):
        sess = transcode_manager.create_session("http://192.168.1.50/rec.m3u8")  # a recording, VLC
        sess.proc = SimpleNamespace(poll=lambda: None, kill=mock.Mock(), wait=mock.Mock())
        self.assertTrue(transcode_manager.touch(sess.session_id, None))
        transcode_manager.stop_session(sess.session_id)
        self.assertNotIn(sess.session_id, transcode_manager.sessions)

    def test_does_not_share_across_incompatible_away_or_caption_modes(self):
        sess = self._make_active_live("CH_6_1", away=False, captions=False)
        self.assertIsNone(transcode_manager.find_live_session("CH_6_1", away=True, captions=False))
        self.assertIsNone(transcode_manager.find_live_session("CH_6_1", away=False, captions=True))
        self.assertEqual(len(sess.viewers), 1)

    def test_force_stop_closes_even_with_multiple_viewers(self):
        sess = self._make_active_live("CH_6_1")
        transcode_manager.add_viewer(sess)
        self.assertEqual(len(sess.viewers), 2)
        transcode_manager.stop_session(sess.session_id, force=True)
        self.assertNotIn(sess.session_id, transcode_manager.sessions)
        sess.proc.kill.assert_called_once()


class StreamLinkTests(unittest.TestCase):
    """VLC on another device can't send the PIN's cookie: a stream's own address goes through without
    it, nothing else does, and nothing at all with network access off."""
    SID = "0123456789abcdef0123456789abcdef"

    def blocked(self, path, lan_on=True):
        with mock.patch.object(lanauth, "network_access_on", return_value=lan_on), \
             mock.patch.object(lanauth, "pin_set", return_value=True), \
             mock.patch.object(lanauth, "own_addresses", return_value=frozenset()):
            return lanauth.blocked(path, "192.168.1.77", None)

    def test_a_stream_link_needs_no_pin(self):
        self.assertIsNone(self.blocked(f"/api/hls/{self.SID}/playlist.m3u8"))
        self.assertIsNone(self.blocked(f"/api/hls/{self.SID}/seg/00001.ts"))

    def test_everything_else_still_needs_it(self):
        for path in ("/api/hls/short/playlist.m3u8", f"/api/hls/{self.SID}", f"/api/transcoded/{self.SID}/playlist.m3u8",
                     "/api/shows", f"/api/hls/{self.SID.upper()}/playlist.m3u8"):
            self.assertEqual(self.blocked(path), "pin_required", path)

    def test_network_access_off_still_blocks_stream_links(self):
        self.assertEqual(self.blocked(f"/api/hls/{self.SID}/playlist.m3u8", lan_on=False), "lan_off")


if __name__ == "__main__":
    unittest.main()
