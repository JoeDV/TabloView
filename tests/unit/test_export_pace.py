try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import unittest
from unittest import mock

import httpx

from app import export_pace
from app.transcode import transcode_manager

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000
variant/index.m3u8
"""
MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXT-X-KEY:METHOD=NONE,URI="key.bin"
#EXTINF:6.000,
seg0.ts
#EXTINF:6.000,
http://other/seg1.ts
#EXT-X-ENDLIST
"""


TABLO_MEDIA = """#EXTM3U
#EXTINF:2.4024,
#EXT-X-BYTERANGE:1760432@0
/stream/segw.ts?abc
#EXTINF:2.43577,
#EXT-X-BYTERANGE:1823976@1760432
/stream/segw.ts?abc
#EXTINF:2.4,
#EXT-X-BYTERANGE:1000
/stream/segw.ts?abc
#EXT-X-ENDLIST
"""


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RelayTests(unittest.TestCase):
    """Exports read through TabloView, which keeps them to a pace that suits the moment."""

    def setUp(self):
        export_pace.local_port = 7070
        self.addCleanup(setattr, export_pace, "local_port", None)

    def test_playlists_point_back_at_tabloview(self):
        r = export_pace.Relay("http://tablo:8887/stream/pl.m3u8")
        master = r.rewrite(MASTER, "http://tablo:8887/stream/pl.m3u8")
        self.assertIn("p1.m3u8", master)
        self.assertEqual(r.targets["p1.m3u8"], ("http://tablo:8887/stream/variant/index.m3u8", 0.0, None))
        media = r.rewrite(MEDIA, "http://tablo:8887/stream/variant/index.m3u8")
        self.assertNotIn("http", media)
        names = [line for line in media.splitlines() if line and not line.startswith("#")]
        self.assertEqual([r.targets[n] for n in names],
                         [("http://tablo:8887/stream/variant/seg0.ts", 6.0, None), ("http://other/seg1.ts", 6.0, None)])
        self.assertIn('URI="a2.bin"', media)  # keys and the like come through here too, unpaced
        self.assertTrue(r.url.startswith("http://127.0.0.1:7070/api/export-relay/"))

    def test_byte_ranges_become_pieces_of_their_own(self):
        # How a Tablo serves a recording: one file, ranges of it (2026-10-22)
        r = export_pace.Relay("http://tablo:8887/stream/pl.m3u8")
        out = r.rewrite(TABLO_MEDIA, "http://tablo:8887/stream/pls.m3u8")
        self.assertNotIn("BYTERANGE", out)
        names = [line for line in out.splitlines() if line and not line.startswith("#")]
        self.assertEqual(len(set(names)), 3)
        self.assertEqual([r.targets[n][1:] for n in names],
                         [(2.4024, (0, 1760432)), (2.43577, (1760432, 1823976)), (2.4, (3584408, 1000))])

    def test_pace_follows_what_is_playing(self):
        clock = Clock()
        r = export_pace.Relay("http://tablo/pl.m3u8", clock=clock)

        def serve(rate):  # as the relay does: hold the piece back, then hand it over
            wait = r.wait_for(6, rate)
            clock.t += wait
            return wait

        # A head start (about BURST_SECONDS at 5x) goes as fast as the Tablo sends
        free = 0
        while serve(export_pace.FAST_RATE) == 0:
            free += 1
        self.assertGreaterEqual(free * 6, export_pace.BURST_SECONDS * export_pace.FAST_RATE - 6)
        # Then a 6-second piece every 1.2 s (5x)...
        self.assertAlmostEqual(serve(export_pace.FAST_RATE), 1.2, places=5)
        # ...every 3 s (2x) once something is playing...
        serve(export_pace.BUSY_RATE)
        self.assertAlmostEqual(serve(export_pace.BUSY_RATE), 3.0, places=5)
        # ...and fast again when it stops
        serve(export_pace.FAST_RATE)
        self.assertAlmostEqual(serve(export_pace.FAST_RATE), 1.2, places=5)

    def test_playback_through_a_relay_isnt_held_back(self):
        # Recordings play through a relay too (FFmpeg reading the Tablo directly lost a packet at
        # every join between its files); playback mustn't wait for the export pace
        export_pace.local_port = 7070
        relay = export_pace.open_relay("http://tablo/pl.m3u8", paced=False)
        self.addCleanup(export_pace.close_relay, relay)
        relay.targets["s1.ts"] = ("http://tablo/segw.ts?a", 6.0, (0, 188))
        ok = httpx.Response(206, content=b"\x47" * 188, headers={"content-type": "video/mp2t"})
        with mock.patch.object(transcode_manager._http, "get", new=mock.AsyncMock(return_value=ok)), \
                mock.patch.object(export_pace.asyncio, "sleep", new=mock.AsyncMock()) as sleep, \
                mock.patch.object(export_pace, "something_playing", new=mock.AsyncMock(return_value=False)):
            for _ in range(20):  # far past the head start
                asyncio.run(export_pace.serve(relay.id, "s1.ts"))
        sleep.assert_not_called()

    def test_a_recording_plays_through_a_relay_and_live_tv_doesnt(self):
        from app import transcode
        export_pace.local_port = 7070
        made = []
        real_open = export_pace.open_relay
        with mock.patch.object(transcode.export_pace, "open_relay", side_effect=lambda u, paced=True: made.append(paced) or real_open(u, paced)):
            for live in (False, True):
                sess = transcode_manager.create_session("http://tablo/pl.m3u8")
                self.addCleanup(transcode_manager.sessions.pop, sess.session_id, None)
                with mock.patch.object(transcode.subprocess, "Popen", side_effect=OSError("no ffmpeg here")):
                    try:
                        asyncio.run(transcode_manager.start_browser_transcode(sess.session_id, "http://tablo/pl.m3u8", live=live))
                    except OSError:
                        pass
                if sess.relay:
                    export_pace.close_relay(sess.relay)
        self.assertEqual(made, [False])  # one unpaced relay, for the recording only

    def test_no_relay_until_tabloviews_port_is_known(self):
        export_pace.local_port = None
        self.assertIsNone(export_pace.open_relay("http://tablo/pl.m3u8"))


class SomethingPlayingTests(unittest.TestCase):
    def check(self, sessions, tuners):
        export_pace._tuners.update(at=0.0, busy=False)
        resp = httpx.Response(200, json=tuners)
        with mock.patch.object(transcode_manager, "sessions", sessions),              mock.patch("app.tablo_client.tablo_manager.request_local", new=mock.AsyncMock(return_value=resp)):
            return asyncio.run(export_pace.something_playing())

    def test_tabloview_playing(self):
        self.assertTrue(self.check({"s": mock.Mock(stopped=False, channel_id=None)}, []))

    def test_live_tv_in_another_app(self):
        self.assertTrue(self.check({}, [{"in_use": True, "channel": "/guide/channels/1", "recording": None}]))

    def test_recordings_in_progress_dont_slow_exports(self):
        self.assertFalse(self.check({}, [{"in_use": True, "channel": "/guide/channels/1", "recording": "/recordings/x"}]))

    def test_nothing(self):
        self.assertFalse(self.check({"s": mock.Mock(stopped=True, channel_id=None)}, [{"in_use": False}]))


if __name__ == "__main__":
    unittest.main()
