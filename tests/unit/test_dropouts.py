import json
import unittest

from app import database as db
from app import dropouts

HEADER = ("Input #0, hls, from 'http://tablo/pl.m3u8':\n"
          "  Stream #0:0: Video: mpeg2video (Main), yuv420p(tv, top first), 1920x1080, 29.97 fps, 29.97 tbr\n"
          "  Stream #0:1: Audio: ac3, 48000 Hz, 5.1(side), fltp, 384 kb/s\n")
THROWN = "[in#0/mpegts @ 01] Packet corrupt (stream = 0, dts = 1), dropping it.\n"
PATCHED = "[vist#0:0/mpeg2video @ 02] [dec:mpeg2video @ 03] corrupt decoded frame\n"


def log_of(seconds):
    """seconds: list of (frames made, damage lines) per second of recording."""
    out, frames = [HEADER], 0
    for t, (made, damage) in enumerate(seconds, start=1):
        out.append(damage)
        frames += made
        out.append(f"frame={frames:5d} fps=120 q=-0.0 size=N/A time=00:00:{t:02d}.00 bitrate=N/A speed=4x\r")
    return "".join(out)


class FindDropoutsTests(unittest.TestCase):
    """Where a weak signal broke up a recording, on the recording's own timeline."""

    def test_a_clean_recording_has_none(self):
        self.assertEqual(dropouts.find_dropouts(log_of([(30, "")] * 40)), [])

    def test_broken_up_seconds_become_one_dropout(self):
        secs = [(30, "")] * 10 + [(20, THROWN * 10)] * 5 + [(30, "")] * 10
        self.assertEqual(dropouts.find_dropouts(log_of(secs)), [{"start": 9.0, "end": 16.0}])

    def test_frozen_picture_where_frames_never_arrived(self):
        # The timeline moves on, but only 5 frames come in each second
        secs = [(30, "")] * 10 + [(5, "")] * 4 + [(30, "")] * 10
        self.assertEqual(dropouts.find_dropouts(log_of(secs)), [{"start": 9.0, "end": 15.0}])

    def test_patched_frames_count_too(self):
        secs = [(30, "")] * 5 + [(30, PATCHED * 12)] * 3 + [(30, "")] * 5
        self.assertEqual(dropouts.find_dropouts(log_of(secs)), [{"start": 4.0, "end": 9.0}])

    def test_a_single_glitch_is_not_a_dropout(self):
        secs = [(30, "")] * 10 + [(29, THROWN)] + [(30, "")] * 10
        self.assertEqual(dropouts.find_dropouts(log_of(secs)), [])

    def test_close_dropouts_merge(self):
        bad = (10, THROWN * 20)
        secs = [(30, "")] * 5 + [bad] * 2 + [(30, "")] * 2 + [bad] * 2 + [(30, "")] * 5
        self.assertEqual(dropouts.find_dropouts(log_of(secs)), [{"start": 4.0, "end": 12.0}])


class SecondsReadTests(unittest.TestCase):
    def test_how_far_ffmpeg_got(self):
        self.assertEqual(dropouts.seconds_read(log_of([(30, "")] * 75)), 75.0)
        self.assertEqual(dropouts.seconds_read(HEADER + "Invalid frame dimensions 0x0.\n"), 0.0)


class PendingTests(unittest.TestCase):
    """Only recordings the Tablo flagged as not clean are read, once each."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM dropouts")
            conn.commit()

    def add(self, eid, clean, state="finished", duration=1800):
        raw = {"video_details": {"clean": clean, "state": state, "duration": duration}}
        db.upsert_episode({"id": eid, "show_id": "s", "show_title": "Show", "path": f"/recordings/{eid}",
                           "title": eid, "air_date": "2026-10-20T00:00Z", "duration": 1800, "raw_json": json.dumps(raw)})

    def test_flagged_recordings_only_and_only_once(self):
        self.add("ep_clean", True)
        self.add("ep_flagged", False)
        self.add("ep_failed_empty", False, state="failed", duration=1)
        self.add("ep_failed", False, state="failed", duration=3000)  # the Tablo won't play failed ones
        self.assertEqual([e["id"] for e in dropouts.pending()], ["ep_flagged"])
        dropouts.save("ep_flagged", "done", [{"start": 9.0, "end": 16.0}])
        self.assertEqual(dropouts.pending(), [])
        self.assertEqual(dropouts.get("ep_flagged")["spans"], [{"start": 9.0, "end": 16.0}])


if __name__ == "__main__":
    unittest.main()
