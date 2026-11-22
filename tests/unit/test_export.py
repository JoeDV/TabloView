import unittest
from pathlib import Path

from app import encoders
from app.transcode import TranscodeManager


class ExportTests(unittest.TestCase):
    def test_original_copies_the_video(self):
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("out.mp4"), None)
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")
        self.assertIn("-readrate", cmd)  # never pull faster than 2x from the Tablo

    def test_smaller_converts_and_deinterlaces(self):
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("out.mp4"), encoders.for_export(encoders.cpu_fallback()))
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "libx264")
        self.assertEqual(cmd[cmd.index("-crf") + 1], "25")  # the smaller-file setting, not playback's
        self.assertIn("bwdif", cmd[cmd.index("-vf") + 1])
        self.assertEqual(cmd[-1], "out.mp4")

    def test_stereo_unless_the_recording_has_surround(self):
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), None)
        self.assertEqual(cmd[cmd.index("-ac") + 1], "2")
        self.assertIn("clev=1.0", cmd[cmd.index("-af") + 1])  # dialogue kept up in the mix-down

    def test_surround_kept_as_51_throughout(self):
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), None, surround=True)
        self.assertEqual(cmd[cmd.index("-ac") + 1], "6")
        self.assertIn("ochl=5.1", cmd[cmd.index("-af") + 1])  # a stereo stretch stays a 5.1 file
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "aac")

    def test_written_as_ts_then_made_into_the_mp4(self):
        # An MP4 isn't playable until FFmpeg closes it; a .ts is good up to wherever it stopped
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("out.part.ts"), None)
        self.assertEqual(cmd[cmd.index("-f") + 1], "mpegts")
        self.assertNotIn("-movflags", cmd)
        remux = TranscodeManager.remux_cmd(Path("out.part.ts"), Path("out.mp4"))
        self.assertEqual(remux[remux.index("-c") + 1], "copy")  # nothing converted twice
        self.assertIn("+faststart", remux)
        self.assertEqual(remux[-1], "out.mp4")

    def test_progress_from_ffmpeg_time(self):
        tail = "frame=1 time=00:01:00.00 bitrate=1\rframe=2 time=00:15:00.50 bitrate=1\r"
        self.assertEqual(TranscodeManager.export_progress(tail, 1800), 50.0)
        self.assertIsNone(TranscodeManager.export_progress("starting", 1800))
        self.assertIsNone(TranscodeManager.export_progress(tail, 0))


class CancelExportTests(unittest.TestCase):
    """Exports can be cancelled (one got stuck on Ubuntu and held up the rest of the queue)."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app import database as db
        db.init_db()
        self.db = db
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.hdr = {"X-TabloView": "1"}

    def test_a_waiting_export_can_be_cancelled_and_then_removed(self):
        import asyncio
        from unittest import mock
        from app.transcode import transcode_manager
        self.db.save_export_job({"job_id": "w1", "filename": "Show.mp4", "filepath": "Show.mp4", "status": "pending",
                                 "progress": 0.0, "created_at": "2026-10-20T00:00:00Z"})
        self.addCleanup(self.db.delete_export_job, "w1")
        task = mock.Mock(done=mock.Mock(return_value=False))
        with mock.patch.dict(transcode_manager.export_tasks, {"w1": task}):
            r = self.client.post("/api/exports/w1/cancel", headers=self.hdr)
        self.assertEqual(r.status_code, 200)
        task.cancel.assert_called_once()
        job = next(j for j in self.db.get_export_jobs() if j["job_id"] == "w1")
        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(self.client.delete("/api/exports/w1", headers=self.hdr).status_code, 200)
        self.assertFalse(any(j["job_id"] == "w1" for j in self.db.get_export_jobs()))

    def test_exports_cut_off_by_closing_tabloview_are_marked_at_start(self):
        # They sat at "Exporting 97%" / "Waiting" for good, even after a reboot (Ubuntu user)
        for job_id, status in (("r1", "downloading"), ("r2", "pending"), ("r3", "completed")):
            self.db.save_export_job({"job_id": job_id, "filename": f"{job_id}.mp4", "filepath": f"{job_id}.mp4",
                                     "status": status, "progress": 97.0, "created_at": "2026-10-20T00:00:00Z"})
            self.addCleanup(self.db.delete_export_job, job_id)
        changed = {j["job_id"] for j in self.db.fail_interrupted_exports()}
        self.assertTrue({"r1", "r2"} <= changed and "r3" not in changed)
        jobs = {j["job_id"]: j for j in self.db.get_export_jobs()}
        self.assertEqual((jobs["r1"]["status"], jobs["r2"]["status"], jobs["r3"]["status"]), ("failed", "failed", "completed"))
        self.assertIn("Interrupted", jobs["r1"]["error"])

    def test_a_finished_export_cant_be_cancelled(self):
        self.assertEqual(self.client.post("/api/exports/nope/cancel", headers=self.hdr).status_code, 404)





class ExportSpeedTests(unittest.TestCase):
    def test_paced_exports_have_no_fixed_speed_limit(self):
        cmd = TranscodeManager.export_cmd("http://127.0.0.1:7070/api/export-relay/x/playlist.m3u8", Path("o.part.ts"), None, None)
        self.assertNotIn("-readrate", cmd)
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), None)
        self.assertEqual(cmd[cmd.index("-readrate") + 1], "2")  # reading directly: twice real time

    def test_a_long_break_left_out_isnt_a_stall(self):
        # FFmpeg writes nothing for minutes while it reads through a break it leaves out
        stalled = TranscodeManager.export_stalled
        self.assertFalse(stalled(now=500, last_change=300, fed_at=495, limit=60))  # the Tablo is still sending
        self.assertTrue(stalled(now=500, last_change=300, fed_at=420, limit=60))   # it stopped
        self.assertTrue(stalled(now=500, last_change=300, fed_at=None, limit=60))  # read directly: time only
        self.assertFalse(stalled(now=500, last_change=480, fed_at=None, limit=60))

    def test_the_relay_notes_when_the_tablo_last_sent(self):
        import asyncio
        from unittest import mock
        from app import export_pace
        clock = [100.0]
        relay = export_pace.Relay("http://tablo/p.m3u8", clock=lambda: clock[0], paced=False)
        relay.targets["s1.ts"] = ("http://tablo/a.ts", 2.4, None)
        export_pace.relays[relay.id] = relay
        resp = mock.Mock(status_code=200, content=b"x", headers={})
        fake = mock.Mock(_http=mock.Mock(get=mock.AsyncMock(return_value=resp)))
        try:
            clock[0] = 250.0
            with mock.patch("app.transcode.transcode_manager", fake):
                asyncio.run(export_pace.serve(relay.id, "s1.ts"))
            self.assertEqual(relay.fed_at, 250.0)
        finally:
            export_pace.close_relay(relay)


if __name__ == "__main__":
    unittest.main()
