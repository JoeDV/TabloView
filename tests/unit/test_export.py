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

    def test_progress_from_ffmpeg_time(self):
        tail = "frame=1 time=00:01:00.00 bitrate=1\rframe=2 time=00:15:00.50 bitrate=1\r"
        self.assertEqual(TranscodeManager.export_progress(tail, 1800), 50.0)
        self.assertIsNone(TranscodeManager.export_progress("starting", 1800))
        self.assertIsNone(TranscodeManager.export_progress(tail, 0))


if __name__ == "__main__":
    unittest.main()
