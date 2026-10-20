import tempfile
import unittest
from pathlib import Path

from app.transcode import TranscodeManager


def progress(speed, elapsed):
    return f"frame= 1000 fps= 29 q=27.0 size=N/A time=00:00:30.00 bitrate=N/A speed={speed}x elapsed={elapsed}    \r"


class FallingBehindTests(unittest.TestCase):
    """Live TV with Smooth motion is switched to standard motion when this PC can't keep up."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def behind(self, *lines):
        (self.dir / "ffmpeg.log").write_text("Input #0, hls\n" + "".join(lines), encoding="utf-8")
        return TranscodeManager._falling_behind(self.dir)

    def test_half_speed_after_30_s_is_behind(self):
        # WTHR with Smooth motion, 2026-10-20
        self.assertTrue(self.behind(progress("0.701", "0:00:12.38"), progress("0.477", "0:02:25.57")))

    def test_keeping_up_is_fine(self):
        self.assertFalse(self.behind(progress("0.943", "0:01:02.98")))
        self.assertFalse(self.behind(progress("0.972", "0:00:56.79")))

    def test_slow_start_isnt_judged_yet(self):
        self.assertFalse(self.behind(progress("0.55", "0:00:20.00")))

    def test_no_log_or_no_progress(self):
        self.assertFalse(TranscodeManager._falling_behind(self.dir / "nowhere"))
        self.assertFalse(self.behind("Opening 'http://...' for reading\n"))


if __name__ == "__main__":
    unittest.main()
