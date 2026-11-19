import asyncio
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import autoexport, encoders, transcode
from app import database as db
from app.config import FFMPEG_PATH
from app.tablo_client import tablo_manager
from app.transcode import TranscodeManager, transcode_manager


def brk(start, end):
    return {"start": start, "end": end}


class CutPiecesTests(unittest.TestCase):
    """Exports without the commercials: the pieces between the breaks are kept, and nothing else."""

    def test_pieces_between_breaks(self):
        self.assertEqual(TranscodeManager.kept_pieces([brk(600, 780), brk(1500, 1650)], 3600),
                         [(0.0, 600), (780, 1500), (1650, None)])

    def test_opening_and_closing_breaks(self):
        # A recording that starts in a break (the Tablo starts a little early), and one ending in one
        self.assertEqual(TranscodeManager.kept_pieces([brk(0, 40), brk(1700, 1800)], 1800), [(40, 1700)])

    def test_overlapping_breaks(self):
        self.assertEqual(TranscodeManager.kept_pieces([brk(100, 200), brk(150, 250)], 0), [(0.0, 100), (250, None)])

    def test_concat_list_uses_the_files_own_times(self):
        text = TranscodeManager.cut_list(Path(r"C:\Exports\Joe's Show.part.ts"), [(0.0, 600), (780, None)], 1.4)
        self.assertEqual(text.splitlines(), [
            r"file 'C:\Exports\Joe'\''s Show.part.ts'", "inpoint 1.400", "outpoint 601.400",
            r"file 'C:\Exports\Joe'\''s Show.part.ts'", "inpoint 781.400"])

    def test_remux_reads_the_list_when_cutting(self):
        cmd = TranscodeManager.remux_cmd(Path("a.part.ts"), Path("a.mp4"), cut_list_path=Path("a.cuts.txt"))
        self.assertEqual(cmd[cmd.index("-f") + 1], "concat")
        self.assertEqual(cmd[cmd.index("-i") + 1], "a.cuts.txt")
        self.assertEqual(cmd[cmd.index("-c") + 1], "copy")

    def test_converted_exports_leave_the_breaks_out_while_converting(self):
        # The pieces are joined before the encoder sees them: clean joins with any encoder
        enc = encoders.for_export(encoders.cpu_fallback())
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), enc, cuts=[brk(600, 780), brk(1500, 1650)])
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("trim=start=0.000:end=600.000", graph)
        self.assertIn("atrim=start=780.000:end=1500.000", graph)
        self.assertIn("trim=start=1650.000,", graph)
        self.assertIn("concat=n=3:v=1:a=1[v][a]", graph)
        self.assertIn("bwdif", graph)
        self.assertNotIn("-vf", cmd)
        self.assertNotIn("-af", cmd)
        plain = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), enc)
        self.assertNotIn("-filter_complex", plain)

    def test_breaks_only_when_asked_and_found(self):
        ep = {"id": "e1"}
        found = {"e1": {"status": "done", "breaks": [brk(900, 1000), brk(100, 200), brk(50, 52)]}}
        with mock.patch("app.database.get_commercials", return_value=found):
            with mock.patch.object(transcode, "load_settings", return_value={"export_cut_breaks": False}):
                self.assertEqual(TranscodeManager.export_breaks(ep), [])
            with mock.patch.object(transcode, "load_settings", return_value={"export_cut_breaks": True}):
                # Sorted; a 2 s blip isn't a break worth a cut
                self.assertEqual(TranscodeManager.export_breaks(ep), [brk(100, 200), brk(900, 1000)])
        with mock.patch("app.database.get_commercials", return_value={"e1": {"status": "failed", "breaks": []}}), \
             mock.patch.object(transcode, "load_settings", return_value={"export_cut_breaks": True}):
            self.assertEqual(TranscodeManager.export_breaks(ep), [])

    def test_cut_mp4_is_the_show_without_the_breaks(self):
        # A real 60 s file: breaks 10-20 s and 40-45 s left out gives 45 s
        with tempfile.TemporaryDirectory() as d:
            ts, mp4 = Path(d) / "it's.part.ts", Path(d) / "a.mp4"
            subprocess.run([FFMPEG_PATH, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30",
                            "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "60", "-c:v", "libx264",
                            "-force_key_frames", "20,45", "-c:a", "aac", "-f", "mpegts", str(ts)], check=True)
            err = asyncio.run(transcode_manager._remux(ts, mp4, None, [brk(10, 20), brk(40, 45)], 60))
            self.assertIsNone(err)
            self.assertFalse(ts.with_name(ts.stem + ".cuts.txt").exists())  # the list is cleaned up
            info = subprocess.run([FFMPEG_PATH, "-hide_banner", "-i", str(mp4)], capture_output=True, text=True).stderr
            h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
            self.assertAlmostEqual(int(h) * 3600 + int(m) * 60 + float(s), 45, delta=0.6)


class AutoExportWaitsForBreaksTests(unittest.TestCase):
    """With exports leaving out the breaks, an automatic export waits until they've been looked for."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("episodes", "auto_exports", "exports", "commercials"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        db.upsert_episode({"id": "c1", "show_id": "showc", "show_title": "showc", "path": "/recordings/series/episodes/c1",
                           "season_number": 1, "episode_number": 1, "title": "c1", "air_date": "2026-11-10T00:00Z",
                           "duration": 1800, "status": "Unwatched", "raw_json": {"video_details": {"state": "finished"}}})
        self.started = []

        async def start(ep, get_url):
            self.started.append(ep["id"])
            db.save_export_job({"job_id": "j1", "episode_id": ep["id"], "title": "t", "filename": "f.mp4", "filepath": "f.mp4",
                                "status": "pending", "progress": 0.0, "file_size": 0, "error": None, "created_at": "2026-11-18"})
            return "j1"
        settings = {"auto_export_shows": ["showc"], "export_cut_breaks": True}
        for p in (mock.patch.object(autoexport, "load_settings", return_value=settings),
                  mock.patch.object(autoexport.commercials, "enabled_shows", return_value=["showc"]),
                  mock.patch.object(autoexport, "_low_space", return_value=False),
                  mock.patch.object(transcode_manager, "start_mp4_export", side_effect=start),
                  mock.patch.object(tablo_manager, "playlist_getter", return_value=None)):
            p.start()
            self.addCleanup(p.stop)

    def test_waits_then_exports(self):
        asyncio.run(autoexport.run_once())
        self.assertEqual(self.started, [])
        db.save_commercials("c1", "done", [brk(600, 780)])
        asyncio.run(autoexport.run_once())
        self.assertEqual(self.started, ["c1"])

    def test_a_failed_search_doesnt_hold_it_up(self):
        db.save_commercials("c1", "failed", error="no")
        asyncio.run(autoexport.run_once())
        self.assertEqual(self.started, ["c1"])


if __name__ == "__main__":
    unittest.main()
