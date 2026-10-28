import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import transcode
from app.config import FFMPEG_PATH
from app.transcode import TranscodeManager


def episode(**over):
    ep = {"id": "ep1", "show_title": "Law & Order", "title": "Pilot <1>", "season_number": 3, "episode_number": 4,
          "description": 'A "case".', "air_date": "2026-10-27T01:00Z", "network": "NBC",
          "raw_json": json.dumps({"episode": {"orig_air_date": "1990-09-13"}})}
    ep.update(over)
    return ep


class ExportMetadataTests(unittest.TestCase):
    """Exports carry their details for Plex, Jellyfin and Kodi: show and season folders, tags in the
    MP4, an optional .nfo (forum, 2026-10-28: exporting metadata with the videos)."""

    def test_tags(self):
        tags = TranscodeManager.export_tags(episode())
        pairs = dict(tags[i + 1].split("=", 1) for i in range(0, len(tags), 2))
        self.assertEqual(pairs["title"], "Pilot <1>")
        self.assertEqual(pairs["show"], "Law & Order")
        self.assertEqual(pairs["season_number"], "3")
        self.assertEqual(pairs["episode_sort"], "4")
        self.assertEqual(pairs["episode_id"], "S03E04")
        self.assertEqual(pairs["date"], "1990-09-13")  # the episode's first airing, not this recording's
        self.assertEqual(pairs["media_type"], "10")

    def test_tags_without_numbers_or_original_date(self):
        tags = TranscodeManager.export_tags(episode(season_number=0, episode_number=0, title=None, raw_json="{}",
                                                    description=None))
        pairs = dict(tags[i + 1].split("=", 1) for i in range(0, len(tags), 2))
        self.assertEqual(pairs["title"], "Law & Order")
        self.assertNotIn("season_number", pairs)
        self.assertNotIn("episode_id", pairs)
        self.assertNotIn("description", pairs)
        self.assertRegex(pairs["date"], r"^2026-10-2[67]$")  # the local day it recorded

    def test_nfo(self):
        nfo = TranscodeManager.export_nfo(episode())
        self.assertIn("<title>Pilot &lt;1&gt;</title>", nfo)
        self.assertIn("<showtitle>Law &amp; Order</showtitle>", nfo)
        self.assertIn("<season>3</season>", nfo)
        self.assertIn("<episode>4</episode>", nfo)
        self.assertIn("<aired>1990-09-13</aired>", nfo)
        self.assertTrue(nfo.startswith("<?xml"))

    def test_folders(self):
        tm = TranscodeManager.__new__(TranscodeManager)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(transcode, "exports_dir", return_value=Path(d)):
            with mock.patch.object(transcode, "load_settings", return_value={}):
                self.assertEqual(tm.export_folder(episode()), Path(d))
            with mock.patch.object(transcode, "load_settings", return_value={"export_show_folders": True}):
                self.assertEqual(tm.export_folder(episode()), Path(d) / "Law & Order" / "Season 03")
                self.assertEqual(tm.export_folder(episode(season_number=0)), Path(d) / "Law & Order")
                self.assertEqual(tm.export_folder(episode(show_title="Mr. Robot.")), Path(d) / "Mr. Robot" / "Season 03")
                self.assertEqual(tm.export_folder(episode(show_title="What? Now:")), Path(d) / "What Now" / "Season 03")

    def test_part_file_on_this_pc_for_network_folders(self):
        local = TranscodeManager.export_part_path("j1", Path(r"D:\Videos\Show - S01E02.mp4"))
        self.assertEqual(local, Path(r"D:\Videos\Show - S01E02.part.ts"))
        net = TranscodeManager.export_part_path("j2", Path(r"\\NAS\Plex\TV\Show\Show - S01E02.mp4"))
        self.assertEqual(net, transcode.TRANSCODE_DIR / "export_j2" / "Show - S01E02.part.ts")
        net.parent.rmdir()

    def test_tags_written_into_mp4(self):
        if not Path(FFMPEG_PATH).with_name("ffprobe" + Path(FFMPEG_PATH).suffix).exists():
            self.skipTest("no ffprobe beside FFmpeg")
        with tempfile.TemporaryDirectory() as d:
            ts, mp4 = Path(d) / "a.part.ts", Path(d) / "a.mp4"
            subprocess.run([FFMPEG_PATH, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30",
                            "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "1", "-c:v", "libx264",
                            "-c:a", "aac", "-f", "mpegts", str(ts)], check=True)
            subprocess.run(TranscodeManager.remux_cmd(ts, mp4, TranscodeManager.export_tags(episode())),
                           check=True, capture_output=True)
            probe = Path(FFMPEG_PATH).with_name("ffprobe" + Path(FFMPEG_PATH).suffix)
            out = subprocess.run([str(probe), "-v", "error", "-show_entries", "format_tags", "-of", "json", str(mp4)],
                                 check=True, capture_output=True, text=True).stdout
            tags = json.loads(out)["format"]["tags"]
            self.assertEqual(tags.get("title"), "Pilot <1>")
            self.assertEqual(tags.get("show"), "Law & Order")
            self.assertEqual(tags.get("season_number"), "3")
            self.assertEqual(tags.get("episode_sort"), "4")
            self.assertEqual(tags.get("synopsis"), 'A "case".')


if __name__ == "__main__":
    unittest.main()
