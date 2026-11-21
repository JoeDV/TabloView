try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import transcode
from app.config import FFMPEG_PATH
from app.transcode import TranscodeManager, transcode_manager


def brk(start, end):
    return {"start": start, "end": end}


class ChapterTests(unittest.TestCase):
    """Exports that keep the commercial breaks mark them as chapters, so Plex, Jellyfin, Kodi and VLC
    can jump past each one (and the recording stays whole)."""

    def test_chapters_around_the_breaks(self):
        text = TranscodeManager.chapters_metadata([brk(0.4, 30), brk(600, 720), brk(1500, 1620)], 1800)
        titles = [l[6:] for l in text.splitlines() if l.startswith("title=")]
        # A break at the very start has no Part before it
        self.assertEqual(titles, ["Commercial break", "Part 1", "Commercial break", "Part 2", "Commercial break", "Part 3"])
        self.assertTrue(text.startswith(";FFMETADATA1\n"))
        self.assertIn("START=600000\nEND=720000\ntitle=Commercial break", text)
        self.assertIn("START=1620000\nEND=1800000\ntitle=Part 3", text)

    def test_only_when_the_breaks_stay_in(self):
        ep = {"id": "e1"}
        found = {"e1": {"status": "done", "breaks": [brk(100, 200)]}}
        with mock.patch("app.database.get_commercials", return_value=found):
            for settings, want in (({}, [brk(100, 200)]),
                                   ({"export_chapters": False}, []),
                                   ({"export_cut_breaks": True}, [])):
                with mock.patch.object(transcode, "load_settings", return_value=settings):
                    self.assertEqual(TranscodeManager.chapter_breaks(ep), want, settings)

    def test_real_mp4_has_the_chapters(self):
        with tempfile.TemporaryDirectory() as d:
            ts, mp4 = Path(d) / "a.part.ts", Path(d) / "a.mp4"
            subprocess.run([FFMPEG_PATH, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30",
                            "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "60", "-c:v", "libx264",
                            "-c:a", "aac", "-f", "mpegts", str(ts)], check=True)
            err = asyncio.run(transcode_manager._remux(ts, mp4, ["-metadata", "title=Show"], None, 60,
                                                       chapters=[brk(20, 30)]))
            self.assertIsNone(err)
            self.assertFalse(ts.with_name(ts.stem + ".chapters.txt").exists())  # cleaned up
            probe = Path(FFMPEG_PATH).with_name(Path(FFMPEG_PATH).name.lower().replace("ffmpeg", "ffprobe"))
            out = subprocess.run([str(probe), "-v", "error", "-show_chapters", "-show_entries", "format_tags=title",
                                  "-of", "json", str(mp4)], capture_output=True, text=True).stdout
            info = json.loads(out)
            got = [(c["tags"]["title"], round(float(c["start_time"])), round(float(c["end_time"]))) for c in info["chapters"]]
            self.assertEqual(got, [("Part 1", 0, 20), ("Commercial break", 20, 30), ("Part 2", 30, 60)])
            self.assertEqual(info["format"]["tags"]["title"], "Show")  # the episode's details are still written


if __name__ == "__main__":
    unittest.main()
