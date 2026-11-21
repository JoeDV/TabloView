try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.config import FFMPEG_PATH
from app.transcode import TranscodeManager, transcode_manager

# As FFmpeg's caption decoder writes it (from a real broadcast's captions)
RAW = r"""1
00:00:02,503 --> 00:00:04,970
<font face="Monospace">{\an7}\h\h\h\h\hI’m supposed to be
\h\htestifying at a hearing.</font>

2
00:00:05,069 --> 00:00:06,997
<font face="Monospace">{\an7}\h\h</font>

3
00:00:07,097 --> 00:00:08,432
<font face="Monospace">{\an7}♪ On Zoom. ♪</font>
"""


class ExportCaptionTests(unittest.TestCase):
    """A .srt of the broadcast's captions beside an export, for Plex, Jellyfin and Kodi."""

    def test_styling_left_out_and_empty_cues_dropped(self):
        self.assertEqual(TranscodeManager.clean_srt(RAW),
                         "1\n00:00:02,503 --> 00:00:04,970\nI’m supposed to be\ntestifying at a hearing.\n\n"
                         "2\n00:00:07,097 --> 00:00:08,432\n♪ On Zoom. ♪\n\n")
        self.assertEqual(TranscodeManager.clean_srt(""), "")

    def test_names_with_quotes_commas_and_brackets(self):
        # Escaped for the movie option (\ ' :), then for the filtergraph (\ ' [ ] , ;)
        v = TranscodeManager.movie_filter_path(Path("C:/TV/Grey's Anatomy, [2026]; x.mp4"))
        self.assertEqual(v, r"C\\:/TV/Grey\\\'s Anatomy\, \[2026\]\; x.mp4")

    def test_no_captions_no_file(self):
        # A real file without captions, in a folder whose name needs escaping: FFmpeg opens it
        # (the escaping works) and finds nothing, so no .srt is left
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "Grey's, [odd]; name"
            folder.mkdir()
            mp4 = folder / "Show's - S01E02, [x].mp4"
            subprocess.run([FFMPEG_PATH, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30", "-t", "3",
                            "-c:v", "libx264", str(mp4)], check=True)
            proc = subprocess.run(TranscodeManager.captions_cmd(mp4, mp4.with_suffix(".srt")), capture_output=True, text=True)
            self.assertNotIn("No such file", proc.stderr)
            self.assertFalse(asyncio.run(transcode_manager.save_captions(mp4)))
            self.assertFalse(mp4.with_suffix(".srt").exists())


if __name__ == "__main__":
    unittest.main()
