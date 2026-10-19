import tempfile
import unittest
from pathlib import Path

from app import encoders
from app.transcode import TranscodeManager, transcode_manager


class StreamEndTests(unittest.TestCase):
    """FFmpeg writes the playlist's end marker even when it crashes, and a player that has seen it
    stops for good; for recordings the marker is added only when the conversion really finished."""

    def plan(self):
        return {"encoder": encoders.cpu_fallback(), "smooth": False, "quality": "auto"}

    def test_recordings_leave_the_end_marker_to_tabloview(self):
        cmd = transcode_manager._build_cmd("http://tablo/p.m3u8", 0, False, self.plan(), Path("s"))
        self.assertIn("omit_endlist", cmd[cmd.index("-hls_flags") + 1])
        resumed = transcode_manager._build_cmd("http://tablo/p.m3u8", 60, False, self.plan(), Path("s"), resume=True)
        self.assertIn("omit_endlist", resumed[resumed.index("-hls_flags") + 1])
        self.assertIn("-start_number", resumed)  # preview frames numbered by position in the recording

    def test_end_marker_added_once(self):
        with tempfile.TemporaryDirectory() as d:
            playlist = Path(d) / "playlist.m3u8"
            playlist.write_text("#EXTM3U\n#EXTINF:3.0,\n00000.ts\n", encoding="utf-8")
            TranscodeManager._end_playlist(Path(d))
            TranscodeManager._end_playlist(Path(d))
            self.assertEqual(playlist.read_text(encoding="utf-8").count("#EXT-X-ENDLIST"), 1)


if __name__ == "__main__":
    unittest.main()
