try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import io
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from tablo_api.models import TabloDevice

from app import dlna, dropouts, export_pace, lanauth, remote, tuner
from app.database import init_db, upsert_episode, upsert_show
from app.main import app
from app.routes.guide import _guide_path
from app.settings import save_settings
from app.tablo_client import tablo_manager
from app.transcode import transcode_manager

DEVICE = TabloDevice(
    sid="SID_AUDIT",
    name="AuditTablo",
    local_url="http://192.168.1.50:8887",
    lighthouse_token="lh-token-audit",
    account_token="acct-token-audit",
    client_id="client-audit-id",
)
HDR = {"X-TabloView": "1"}


class GuidePathValidationTests(unittest.TestCase):
    def test_valid_guide_paths_accepted(self):
        for p in (
            "/guide/series/163949",
            "guide/movies/42",
            "/guide/sports/99/events",
            "/guide/episodes/12345",
            "/guide/events/67890",
            "/guide/airings/555",
        ):
            self.assertTrue(_guide_path(p).startswith("/guide/"))

    def test_non_guide_and_traversal_paths_rejected(self):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        bad_paths = [
            "/server/info",
            "/recordings/series/123",
            "/guide/series/../server/info",
            "/guide/series/123?foo=bar",
            "/guide/series/123#frag",
            "",
        ]
        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch.object(tablo_manager, "request_local", new=mock.AsyncMock()) as req:
            for bad in bad_paths:
                r1 = client.get("/api/guide/series", params={"path": bad})
                r2 = client.post("/api/guide/series/schedule", json={"path": bad, "rule": "new"}, headers=HDR)
                r3 = client.post("/api/guide/episodes/schedule", json={"path": bad, "scheduled": True}, headers=HDR)
                r4 = client.post("/api/guide/conflicts/swap", json={"record_path": bad, "skip_path": "/guide/airings/1"}, headers=HDR)
                r5 = client.get("/api/guide/series/episodes", params={"series_path": bad})
                for r in (r1, r2, r3, r4, r5):
                    self.assertEqual(r.status_code, 400, f"Expected 400 for {bad!r}, got {r.status_code}")
            req.assert_not_called()


class HostOnlyGuardTests(unittest.TestCase):
    def setUp(self):
        save_settings({"allow_lan": True})
        lanauth.set_pin("1234")
        self.cookie = lanauth.make_token()

    def tearDown(self):
        save_settings({"allow_lan": False})

    def test_debug_and_devcheck_blocked_from_lan(self):
        lan = TestClient(app, base_url="http://192.168.1.10:7070", client=("192.168.1.99", 50000))
        lan.cookies.set(lanauth.COOKIE, self.cookie)
        self.assertEqual(lan.get("/api/debug/endpoints").status_code, 403)
        self.assertEqual(
            lan.post("/api/dev/check", json={"method": "GET", "url": "/api/shows"}, headers=HDR).status_code,
            403,
        )

    def test_devcheck_allowed_from_this_pc(self):
        local = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        r = local.post("/api/dev/check", json={"method": "GET", "url": "/api/shows"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])


class RemoteScreenBoundsTests(unittest.TestCase):
    def setUp(self):
        remote.reopen()

    def test_screens_capped_and_stale_evicted(self):
        now = [100.0]
        clk = lambda: now[0]
        for i in range(remote.MAX_SCREENS + 15):
            now[0] += 0.1
            remote.screen(f"screen_{i:03d}", "TV", clock=clk)
        self.assertLessEqual(len(remote.screens), remote.MAX_SCREENS)
        self.assertIn(f"screen_{remote.MAX_SCREENS + 14:03d}", remote.screens)
        self.assertNotIn("screen_000", remote.screens)


class DlnaAndExportPaceTests(unittest.TestCase):
    def test_soap_body_size_limit(self):
        client = TestClient(tuner.app, base_url="http://127.0.0.1:5004", client=("127.0.0.1", 50000))
        big = b"x" * (dlna.MAX_SOAP_BYTES + 1)
        r = client.post("/dlna/control/cds", content=big, headers={"SOAPACTION": '"urn:x#Browse"'})
        self.assertEqual(r.status_code, 413)

    def test_export_pace_notices_active_tuner_streams(self):
        tuner.streams.clear()
        tuner.streams[999999] = {"channel": "6.1 WRTV", "client": "192.168.1.20", "since": 0.0}
        try:
            self.assertTrue(asyncio.run(export_pace.something_playing()))
        finally:
            tuner.streams.pop(999999, None)

    def test_dlna_recording_tracks_stream_and_runs_full_speed(self):
        init_db()
        upsert_show({"id": "dlna-show", "title": "DLNA Show", "episode_count": 1, "unwatched_count": 1})
        upsert_episode({
            "id": "ep_dlna_1",
            "show_id": "dlna-show",
            "show_title": "DLNA Show",
            "path": "/recordings/series/episodes/999",
            "title": "Pilot",
            "duration": 1800,
            "raw_json": {"video_details": {"state": "finished", "duration": 1800}},
        })

        fake_proc = SimpleNamespace(
            pid=777777,
            stdout=io.BytesIO(b"TSDATA"),
            kill=mock.Mock(),
            wait=mock.Mock(),
        )
        seen_in_streams = []

        real_read = fake_proc.stdout.read

        def spy_read(n=-1):
            seen_in_streams.append(777777 in tuner.streams)
            return real_read(n)

        fake_proc.stdout.read = spy_read
        client = TestClient(tuner.app, base_url="http://127.0.0.1:5004", client=("127.0.0.1", 50000))

        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch.object(tablo_manager, "get_airing_watch_url",
                               new=mock.AsyncMock(return_value={"playlist_url": "http://192.168.1.50/p.m3u8", "token": "tok-dlna"})), \
             mock.patch.object(tablo_manager, "end_watch_session", new=mock.AsyncMock()) as end_watch, \
             mock.patch("app.dlna.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.childproc.tie_to_app"), \
             mock.patch("app.transcode.run_at_full_speed") as full_speed, \
             mock.patch("app.encoders.choose", return_value={"name": "cpu", "label": "CPU", "args": [], "pix_fmt": "yuv420p"}):
            r = client.get("/dlna/rec/ep_dlna_1.ts")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.content, b"TSDATA")
            full_speed.assert_called_once_with(fake_proc)
            self.assertTrue(any(seen_in_streams))
            self.assertNotIn(777777, tuner.streams)
            end_watch.assert_called()


class VlcSessionTokenTests(unittest.TestCase):
    def tearDown(self):
        for sid in list(transcode_manager.sessions.keys()):
            transcode_manager.sessions.pop(sid, None)

    def test_episode_m3u_records_tablo_token(self):
        init_db()
        upsert_show({"id": "vlc-show", "title": "VLC Show", "episode_count": 1, "unwatched_count": 1})
        upsert_episode({
            "id": "ep_vlc_1",
            "show_id": "vlc-show",
            "show_title": "VLC Show",
            "path": "/recordings/series/episodes/555",
            "title": "Test Ep",
            "duration": 1800,
        })
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch.object(tablo_manager, "get_airing_watch_url",
                               new=mock.AsyncMock(return_value={"playlist_url": "http://192.168.1.50/ep.m3u8", "token": "tok-ep-vlc"})):
            r = client.get("/api/episodes/ep_vlc_1/playlist.m3u")
        self.assertEqual(r.status_code, 200)
        sessions = [s for s in transcode_manager.sessions.values() if s.tablo_token == "tok-ep-vlc"]
        self.assertEqual(len(sessions), 1)

    def test_live_vlc_m3u_creates_tracked_session(self):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        fake_stream = SimpleNamespace(playlist_url="http://192.168.1.50/live.m3u8", token="tok-live-vlc")
        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch("app.routes.live.TabloClient") as tc_cls:
            tc_cls.return_value.watch.return_value = fake_stream
            r = client.get("/api/live/vlc/CH_6_1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/api/hls/", r.text)
        sessions = [s for s in transcode_manager.sessions.values() if s.tablo_token == "tok-live-vlc"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].channel_id, "CH_6_1")


class DropoutsBatchAndActivityLockTests(unittest.TestCase):
    def test_dropouts_get_many(self):
        init_db()
        dropouts.save("ep_drop_a", "done", [{"start": 10.0, "end": 14.0}])
        dropouts.save("ep_drop_b", "done", [])
        self.assertEqual(dropouts.get_many([]), {})
        got = dropouts.get_many(["ep_drop_a", "ep_drop_b", "ep_drop_missing"])
        self.assertEqual(set(got.keys()), {"ep_drop_a", "ep_drop_b"})
        self.assertEqual(got["ep_drop_a"]["spans"], [{"start": 10.0, "end": 14.0}])
        self.assertEqual(got["ep_drop_b"]["spans"], [])

    def test_concurrent_lan_activity_writes_do_not_drop_events(self):
        lanauth.clear_activity()
        errors = []

        def worker(i):
            try:
                lanauth.note_event(f"192.168.1.{10 + i}", "Chrome/120", "wrong_pin", now=1000.0 + i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(lanauth.activity(now=1020.0)["events"]), 12)


if __name__ == "__main__":
    unittest.main()
