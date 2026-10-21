try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import tempfile
import unittest
from pathlib import Path

from app.reception import Meter, state_for



def header(size="1920x1080", fps="29.97", out_fps="29.97"):
    return (
        "Input #0, hls, from 'http://192.168.1.10/stream/pl.m3u8':\n"
        f"  Stream #0:0[0x0]: Video: mpeg2video (Main), yuv420p(tv), {size} [SAR 1:1 DAR 16:9], {fps} fps, {fps} tbr\n"
        "  Stream #0:1[0x0]: Audio: ac3, 48000 Hz, 5.1(side), fltp, 384 kb/s\n"
        "Output #0, hls, to 'playlist.m3u8':\n"
        f"  Stream #0:0: Video: h264, nv12(tv, progressive), {size}, q=2-31, {out_fps} fps, 90k tbn\n"
        "  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo\n"
    )


CORRUPT_VIDEO = "[in#0/mpegts @ 000001] Packet corrupt (stream = 0, dts = 123456), dropping it.\n"
CORRUPT_AUDIO = "[in#0/mpegts @ 000001] Packet corrupt (stream = 1, dts = 123456), dropping it.\n"
PATCHED = ("[mpeg2video @ 000002835f4dc000] concealing 173 DC, 173 AC, 173 MV errors in P frame\n"
           "[vist#0:0/mpeg2video @ 000002835f4c2e40] [dec:mpeg2video @ 000002835f4bdfc0] corrupt decoded frame\n")


def progress(frame, seconds, dup=0):
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    dup_part = f" dup={dup} drop=0" if dup else ""
    return (f"frame={frame:5d} fps= 30 q=27.0 size=N/A time={int(h):02d}:{int(m):02d}:{s:05.2f} "
            f"bitrate=N/A{dup_part} speed=1x elapsed=0:00:10.00    \r")


class MeterTests(unittest.TestCase):
    """The meter turns FFmpeg's log into 'share of the picture arriving intact'."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name) / "ffmpeg.log"
        self.log.write_text("", encoding="utf-8")
        self.meter = Meter(self.log)
        self.frame, self.timeline, self.dup, self.t = 0, 0.0, 0, 0
        self.fps = 29.97

    def write(self, text):
        with open(self.log, "a", encoding="utf-8", newline="") as f:
            f.write(text)

    def tick(self, frames=None, timeline=None, dup=0, extra=""):
        """One second: FFmpeg made `frames` (default: a second's worth) covering `timeline` seconds."""
        self.t += 1
        timeline = 1.0 if timeline is None else timeline
        frames = round(timeline * self.fps) if frames is None else frames
        self.write(extra)
        if frames or dup:
            self.frame += frames
            self.timeline += timeline
            self.dup += dup
            self.write(progress(self.frame, self.timeline, self.dup))
        return self.meter.sample(now=self.t)

    def start(self, seconds=20, **kw):
        """Tuned and past the start-up period."""
        self.write(header(**kw))
        self.meter.sample(now=0)
        for _ in range(seconds):
            self.tick()

    def report(self):
        return self.meter.report(now=self.t)

    def test_nothing_until_converting_starts(self):
        self.assertIsNone(self.meter.sample(now=0))
        self.write(header())
        self.assertIsNone(self.meter.sample(now=1))
        self.assertEqual(self.meter.report(now=1)["state"], "starting")

    def test_clean_signal_is_100(self):
        self.start()
        r = self.report()
        self.assertEqual((r["state"], r["score"], r["worst"], r["dropouts"]), ("clean", 100, None, 0))

    def test_thrown_away_frames_lower_the_score(self):
        self.start()
        self.assertAlmostEqual(self.tick(extra=CORRUPT_VIDEO * 3), 90.0, delta=0.2)
        self.assertAlmostEqual(self.tick(extra=CORRUPT_VIDEO * 15), 50.0, delta=0.2)

    def test_thrown_away_frames_arent_counted_twice(self):
        # A thrown-away frame also leaves a gap in the timeline: half a second's frames lost is 50%, not 0%
        self.start()
        self.assertAlmostEqual(self.tick(frames=15, extra=CORRUPT_VIDEO * 15), 50.0, delta=1)
        for _ in range(5):
            self.tick()
        self.assertGreater(self.report()["worst"]["score"], 45)

    def test_frames_the_decoder_patched_count_as_damaged(self):
        # From a live WTHR session: damaged frames reach the decoder, which conceals the broken parts
        self.start()
        self.assertAlmostEqual(self.tick(extra=PATCHED * 2), 93.3, delta=0.2)

    def test_audio_damage_doesnt_count_against_the_picture(self):
        audio = "[aist#0:1/ac3 @ 000002835f4c2f00] [dec:ac3 @ 000002835f4be000] corrupt decoded frame\n"
        self.start()
        self.assertEqual(self.tick(extra=CORRUPT_AUDIO * 5 + audio), 100.0)

    def test_chunky_delivery_isnt_a_dropout(self):
        # Live TV as WTHR delivered it: a chunk FFmpeg races through, then nothing for 2 s, again and
        # again, with exactly the frames due each time (199 frames for 6.64 s of timeline)
        self.start()
        for _ in range(20):
            self.tick(timeline=3.0)
            self.tick(frames=0, timeline=0)
            self.tick(frames=0, timeline=0)
        r = self.report()
        self.assertEqual((r["dropouts"], r["worst"], r["state"]), (0, None, "clean"))

    def test_the_encoder_holding_frames_back_isnt_a_loss(self):
        # Second by second the timeline runs a few frames ahead of the frames made, then evens out
        self.start()
        for _ in range(10):
            self.tick(frames=25)
            self.tick(frames=35)
        self.assertIsNone(self.report()["worst"])

    def test_frames_that_never_arrive_count_as_lost(self):
        # 3 s with nothing, then the stream carries on from where it is now: the timeline jumps
        self.start()
        for _ in range(3):
            self.assertIsNone(self.tick(frames=0, timeline=0))
        self.tick(frames=30, timeline=4.0)  # 4 s of timeline, only 1 s of frames
        for _ in range(5):
            self.tick()
        r = self.report()
        self.assertEqual(r["dropouts"], 1)
        self.assertLess(r["worst"]["score"], 30)
        self.assertEqual(r["state"], "clean")  # and it's fine again now

    def test_smooth_motion_gaps_filled_with_copies_count_as_lost(self):
        # Smooth motion: 60 frames a second out; FFmpeg fills a gap with copies and counts them
        self.fps = 59.94
        self.write(header(out_fps="59.94"))
        self.meter.sample(now=0)
        for _ in range(20):
            self.tick()
        self.tick(frames=180, timeline=3.0, dup=120)  # 3 s of timeline, 2 s of it copies
        self.assertLess(self.report()["worst"]["score"], 50)

    def test_start_up_copies_are_ignored(self):
        self.write(header())
        self.meter.sample(now=0)
        self.tick(frames=30, timeline=1.0, dup=75)
        self.tick(frames=30, timeline=1.0, dup=40)
        for _ in range(20):
            self.tick()
        self.assertIsNone(self.report()["worst"])

    def test_a_long_stop_shows_no_signal_while_it_lasts(self):
        self.start()
        for _ in range(6):
            self.tick(frames=0, timeline=0)
        r = self.report()
        self.assertEqual((r["state"], r["score"]), ("no_signal", 0.0))
        self.assertEqual(r["history"][-1][1], 0.0)

    def test_a_restarted_ffmpeg_starts_counting_again(self):
        self.start()
        self.write("\n===== restart 1 =====\n" + header())
        self.frame, self.timeline = 0, 0.0
        for _ in range(20):
            self.tick()
        self.assertIsNone(self.report()["worst"])

    def test_a_line_split_across_reads_is_counted_once(self):
        self.start()
        self.write(CORRUPT_VIDEO[:20])
        self.meter.sample(now=self.t + 0.5)
        self.assertAlmostEqual(self.tick(extra=CORRUPT_VIDEO[20:]), 96.7, delta=0.2)

    def test_720p_channels_use_their_frame_rate(self):
        self.fps = 59.94
        self.start(size="1280x720", fps="59.94", out_fps="59.94")
        self.assertAlmostEqual(self.tick(extra=CORRUPT_VIDEO * 6), 90.0, delta=0.2)

    def test_history_is_five_minutes(self):
        self.start(seconds=400)
        hist = self.report()["history"]
        self.assertEqual(len(hist), 300)
        self.assertEqual(hist[-1], [0.0, 100.0])

    def test_states(self):
        self.assertEqual([state_for(s) for s in (None, 100, 95, 61, 18, 0)],
                         ["starting", "clean", "minor", "breaking", "losing", "no_signal"])


if __name__ == "__main__":
    unittest.main()
