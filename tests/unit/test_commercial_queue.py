import asyncio
import unittest
from unittest import mock

from app import commercials
from app import database as db


def episode(id, show, status="Unwatched", state="finished", air="2026-10-10T00:00Z"):
    return {"id": id, "show_id": show, "show_title": show, "path": f"/recordings/series/episodes/{id}", "season_number": 1,
            "episode_number": 1, "title": id, "air_date": air, "duration": 1800, "status": status,
            "raw_json": {"video_details": {"state": state}}}


class CommercialQueueTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM commercials")
            conn.commit()
        for ep in (episode("a1", "showa", air="2026-10-11T00:00Z"), episode("a2", "showa"),
                   episode("a3", "showa", status="Watched"), episode("b1", "showb", status="Watched"),
                   episode("b2", "showb", state="recording")):
            db.upsert_episode(ep)
        self.settings = {"commercial_shows": [], "commercial_episodes": []}
        for p in (mock.patch.object(commercials, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(commercials, "save_settings", side_effect=lambda u: self.settings.update(u))):
            p.start()
            self.addCleanup(p.stop)

    def ids(self):
        return [e["id"] for e in commercials.pending()]

    def test_a_show_does_its_unwatched_finished_recordings_newest_first(self):
        self.settings["commercial_shows"] = ["showa"]
        self.assertEqual(self.ids(), ["a1", "a2"])

    def test_a_single_recording_goes_first_even_if_watched_or_its_show_is_off(self):
        self.settings["commercial_shows"] = ["showa"]
        commercials.queue_episode("b1")
        self.assertEqual(self.ids(), ["b1", "a1", "a2"])

    def test_done_or_still_recording_is_left_out(self):
        commercials.queue_episode("b2")
        commercials.queue_episode("a3")
        db.save_commercials("a3", "done", [])
        self.assertEqual(self.ids(), [])

    def test_unwatched_ones_found_by_the_old_detector_are_done_again(self):
        # Colour alone found 47 s of a 4-minute Hell's Kitchen break; the logo finds all of it
        self.settings["commercial_shows"] = ["showa"]
        db.save_commercials("a1", "done", [{"start": 10.0, "end": 57.0}])  # method 1
        db.save_commercials("a2", "done", [], method=commercials.METHOD)
        self.assertEqual(self.ids(), ["a1"])
        db.save_commercials("a1", "done", [{"start": 10.0, "end": 250.0}], method=commercials.METHOD)
        self.assertEqual(self.ids(), [])


class ReadSpeedTests(unittest.TestCase):
    """Recordings are read as fast as they come, unless another app is watching live TV from the Tablo."""

    def rate(self, tablo_busy):
        seen = []

        def fake_analyze(url, log_path, stop, progress=None, rate=None):
            seen.append(rate)
            return None  # as if stopped: nothing saved

        with mock.patch("app.tablo_client.tablo_manager.get_airing_watch_url", new=mock.AsyncMock(return_value={"playlist_url": "http://tablo/pl.m3u8"})),                 mock.patch("app.export_pace.something_playing", new=mock.AsyncMock(return_value=tablo_busy)),                 mock.patch.object(commercials, "_analyze", side_effect=fake_analyze),                 mock.patch.object(commercials, "_busy", return_value=False):
            asyncio.run(commercials.analyze({"id": "e1", "path": "/recordings/series/episodes/e1", "show_title": "s"}))
        return seen[0]

    def test_uncapped_when_nothing_else_is_watching(self):
        self.assertIsNone(self.rate(False))

    def test_real_time_multiple_while_live_tv_plays_elsewhere(self):
        self.assertEqual(self.rate(True), commercials.READ_RATE)

    def test_ffmpeg_gets_readrate_only_when_capped(self):
        made = []
        fake = mock.Mock(stdout=mock.Mock(read=lambda n: b""), returncode=0, wait=lambda: 0, poll=lambda: 0)
        with mock.patch.object(commercials.subprocess, "Popen", side_effect=lambda cmd, **k: made.append(cmd) or fake),                 mock.patch.object(commercials.childproc, "tie_to_app"):
            for rate in (None, 4):
                commercials._analyze("http://x/pl.m3u8", commercials.TRANSCODE_DIR / "t_rate.log", __import__("threading").Event(), None, rate)
        (commercials.TRANSCODE_DIR / "t_rate.log").unlink(missing_ok=True)
        self.assertNotIn("-readrate", made[0])
        self.assertEqual(made[1][made[1].index("-readrate") + 1], "4")


if __name__ == "__main__":
    unittest.main()
