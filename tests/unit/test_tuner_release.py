try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import unittest
from unittest import mock

import requests
from fastapi.testclient import TestClient

from app.main import app
from app.routes import live
from app.tablo_client import tablo_manager
from app.transcode import transcode_manager


HDR = {"X-TabloView": "1"}


class EndedSessionWaitTests(unittest.IsolatedAsyncioTestCase):
    """Changing channels: the old watch session is ended on the Tablo before the new one is asked for."""

    async def test_tuning_waits_for_the_old_session_to_end(self):
        order = []

        async def slow_end(token):
            await asyncio.sleep(0.05)
            order.append(f"ended {token}")

        sess = transcode_manager.create_session("http://tablo/old.m3u8")
        sess.tablo_token = "old"
        with mock.patch.object(tablo_manager, "end_watch_session", new=slow_end):
            transcode_manager.stop_session(sess.session_id)
            await transcode_manager.wait_for_ended_sessions()
            order.append("tune")
        self.assertEqual(order, ["ended old", "tune"])

    async def test_a_stuck_end_request_doesnt_block_tuning_for_long(self):
        async def never_ends(token):
            await asyncio.sleep(60)

        sess = transcode_manager.create_session("http://tablo/old.m3u8")
        sess.tablo_token = "old"
        with mock.patch.object(tablo_manager, "end_watch_session", new=never_ends):
            transcode_manager.stop_session(sess.session_id)
            loop = asyncio.get_running_loop()
            start = loop.time()
            await transcode_manager.wait_for_ended_sessions(timeout=0.1)
            self.assertLess(loop.time() - start, 1)
        for t in list(transcode_manager._ending):
            t.cancel()


class AllTunersBusyTests(unittest.IsolatedAsyncioTestCase):
    async def _message(self, status):
        with mock.patch.object(live, "get_tuner_status", new=mock.AsyncMock(return_value=status)):
            return await live.all_tuners_busy_message()

    async def test_explains_held_and_recording_tuners(self):
        msg = await self._message({"total": 2, "available": 0, "held": 1, "recording": 1})
        self.assertIn("All 2 antenna tuners are busy", msg)
        self.assertIn("1 recording", msg)
        self.assertIn("still held by the Tablo", msg)
        self.assertNotIn("watching live TV", msg)

    async def test_no_message_when_a_tuner_is_free_or_unknown(self):
        self.assertIsNone(await self._message({"total": 2, "available": 1, "held": 0, "recording": 1}))
        self.assertIsNone(await self._message({"total": 0, "available": 0}))


class TuneRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def test_refused_with_a_tuner_free_means_the_station_cant_be_picked_up(self):
        # 69.1 WDTI, 2026-10-20: the Tablo answered 503 with a tuner free (that tuned 6.1 straight after)
        r = self._tune(None, refused=requests.HTTPError("503 Server Error", response=mock.Mock(status_code=503)))
        self.assertEqual(r.status_code, 502)
        self.assertIn("can't pick up this channel", r.json()["detail"])

    def _tune(self, busy, refused=None):
        refused = refused or requests.HTTPError("500 Server Error")
        with mock.patch.object(type(tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)), \
             mock.patch.object(tablo_manager, "device", new=mock.Mock()), \
             mock.patch.object(live.TabloClient, "__init__", return_value=None), \
             mock.patch.object(live.TabloClient, "watch", side_effect=refused), \
             mock.patch.object(live, "all_tuners_busy_message", new=mock.AsyncMock(return_value=busy)):
            return self.client.post("/api/live/tune", json={"channel_id": "S123", "kind": "ota"}, headers=HDR)

    def test_all_tuners_busy_is_a_409_with_the_reason(self):
        r = self._tune("All 2 antenna tuners are busy: 2 watching live TV. Recordings still play.")
        self.assertEqual(r.status_code, 409)
        self.assertIn("antenna tuners are busy", r.json()["detail"])

    def test_other_failures_stay_errors(self):
        self.assertEqual(self._tune(None).status_code, 500)


class MeasureRouteTests(unittest.TestCase):
    """Antenna helper: a channel is tuned only to be measured, and stopping it ends the Tablo session."""

    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def test_measure_starts_a_measure_only_session_and_stop_ends_it(self):
        stream = mock.Mock(playlist_url="http://tablo/pl.m3u8", token="tok")
        ended = []

        async def fake_end(token):
            ended.append(token)

        with mock.patch.object(type(tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)), \
             mock.patch.object(tablo_manager, "device", new=mock.Mock()), \
             mock.patch.object(live.TabloClient, "__init__", return_value=None), \
             mock.patch.object(live.TabloClient, "watch", return_value=stream), \
             mock.patch.object(transcode_manager, "start_measure") as start_measure, \
             mock.patch.object(tablo_manager, "end_watch_session", new=fake_end):
            r = self.client.post("/api/live/measure", json={"channel_id": "S123"}, headers=HDR)
            self.assertEqual(r.status_code, 200)
            sid = r.json()["session_id"]
            sess = transcode_manager.get_session(sid)
            self.assertEqual(sess.tablo_token, "tok")
            start_measure.assert_called_once_with(sess, "http://tablo/pl.m3u8")
            self.client.post("/api/live/stop", json={"session_id": sid}, headers=HDR)
        self.assertEqual(ended, ["tok"])
        self.assertIsNone(transcode_manager.get_session(sid))


if __name__ == "__main__":
    unittest.main()
