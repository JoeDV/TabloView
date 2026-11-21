import unittest
from pathlib import Path
from unittest import mock

from app import encoders
from app.transcode import TranscodeManager, transcode_manager


class EncoderChoiceTests(unittest.TestCase):
    def setUp(self):
        encoders._failed.clear()
        self.addCleanup(encoders._failed.clear)

    def test_prefers_a_working_graphics_chip(self):
        with mock.patch.object(encoders, "_working", ["qsv"]):
            enc = encoders.choose("auto")
        self.assertEqual(enc["name"], "qsv")
        self.assertTrue(enc["hardware"])
        self.assertIn("h264_qsv", enc["args"])

    def test_cpu_when_no_graphics_chip(self):
        with mock.patch.object(encoders, "_working", []):
            enc = encoders.choose("auto")
        self.assertEqual(enc["name"], "cpu")
        self.assertIn("veryfast", enc["args"])

    def test_failed_encoder_is_skipped(self):
        with mock.patch.object(encoders, "_working", ["qsv", "nvenc"]):
            encoders.mark_failed("qsv")
            self.assertEqual(encoders.choose("auto")["name"], "nvenc")

    def test_best_and_fastest(self):
        with mock.patch.object(encoders, "_working", []):
            self.assertIn("20", encoders.choose("best")["args"])
            self.assertIn("ultrafast", encoders.choose("fastest")["args"])


class CommandTests(unittest.TestCase):
    def plan(self, **settings):
        with mock.patch.object(encoders, "_working", ["qsv"]), \
                mock.patch("app.transcode.load_settings", return_value={"video_quality": "auto", "smooth_motion": None, **settings}):
            return transcode_manager._video_plan(passthrough=False)

    def cmd(self, plan, live=False):
        return " ".join(transcode_manager._build_cmd("http://tablo/x.m3u8", 0, live, plan, Path("out")))

    def test_smooth_motion_is_opt_in(self):
        c = self.cmd(self.plan())
        self.assertIn("bwdif=mode=send_frame:deint=interlaced", c)
        self.assertIn("fps=30000/1001", c)  # 720p channels too, not only 1080i
        self.assertIn("-force_key_frames", c)
        self.assertIn("192k", c)

    def test_smooth_motion_when_turned_on(self):
        self.assertIn("mode=send_field", self.cmd(self.plan(smooth_motion=True)))

    def test_resume_appends_to_the_same_playlist(self):
        c = transcode_manager._build_cmd("http://tablo/x.m3u8", 300, False, self.plan(), Path("out"), resume=True)
        self.assertIn("append_list+discont_start", " ".join(c))
        self.assertEqual(c[c.index("-ss") + 1], "300")

    def test_passthrough_copies_video(self):
        plan = transcode_manager._video_plan(passthrough=True)
        c = self.cmd(plan, live=True)
        self.assertIn("-c:v copy", c)
        self.assertNotIn("bwdif", c)

    def test_recordings_are_read_at_twice_real_time(self):
        self.assertIn("-readrate 2", self.cmd(self.plan()))
        self.assertNotIn("-readrate", self.cmd(self.plan(), live=True))



class PlatformEncoderTests(unittest.TestCase):
    """Macs use Apple's VideoToolbox (they always encoded on the CPU before); PCs the others."""

    def test_macs_try_videotoolbox(self):
        self.assertEqual(encoders.candidates("darwin"), ["videotoolbox"])

    def test_pcs_try_the_pc_encoders(self):
        self.assertEqual(encoders.candidates("win32"), ["qsv", "nvenc", "amf"])
        # Linux also has VAAPI (before AMF, which there needs AMD's own driver)
        self.assertEqual(encoders.candidates("linux"), ["qsv", "nvenc", "vaapi", "vaapi_lp", "amf"])

    def test_videotoolbox_exports_aim_for_a_smaller_file(self):
        enc = {"name": "videotoolbox", "label": "Apple VideoToolbox", "hardware": True, "args": [], "pix_fmt": "nv12"}
        args = encoders.for_export(enc)["args"]
        self.assertEqual(args[:2], ["-c:v", "h264_videotoolbox"])
        self.assertEqual(args[args.index("-b:v") + 1], "5M")


class VaapiTests(unittest.TestCase):
    """Linux (a Docker user's Intel UHD 630): frames go up to the chip after the filters, no -pix_fmt."""

    def setUp(self):
        encoders._failed.clear()
        self.addCleanup(encoders._failed.clear)

    def enc(self, quality="auto"):
        with mock.patch.object(encoders, "_working", ["vaapi"]):
            return encoders.choose(quality)

    def test_playback(self):
        plan = {"encoder": self.enc(), "smooth": False, "quality": "auto", "size": None}
        c = transcode_manager._build_cmd("http://tablo/x.m3u8", 0, False, plan, Path("out"))
        vf = c[c.index("-vf") + 1]
        self.assertTrue(vf.startswith("bwdif=") and vf.endswith(",format=nv12,hwupload"), vf)
        self.assertEqual(c[c.index("-vaapi_device") + 1], "/dev/dri/renderD128")
        self.assertIn("h264_vaapi", c)
        self.assertNotIn("-pix_fmt", c[:c.index("-f")])  # (the preview frames are a separate output)
        # The preview frames come from the decoder, not the chip
        self.assertIn("fps=1/5:round=down,scale=256:-2", c)

    def test_best_and_away(self):
        self.assertEqual(self.enc("best")["args"][-1], "20")
        capped = encoders.capped(self.enc(), 3000)
        self.assertIn("VBR", capped["args"])
        self.assertIn("-vaapi_device", capped["args"])

    def test_export_with_breaks_left_out(self):
        enc = encoders.for_export(self.enc())
        cmd = TranscodeManager.export_cmd("http://tablo/p.m3u8", Path("o.part.ts"), enc,
                                                    cuts=[{"start": 600, "end": 780}])
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("concat=n=2:v=1:a=1[vj][a];[vj]format=nv12,hwupload[v]", graph)
        self.assertEqual(cmd[cmd.index("-qp") + 1], "26")
        self.assertNotIn("-pix_fmt", cmd)

    def test_dlna_conversion(self):
        from app import tuner
        c = tuner.stream_cmd("http://tablo/live.m3u8", self.enc())
        self.assertTrue(c[c.index("-vf") + 1].endswith("fps=30000/1001,format=nv12,hwupload"))
        self.assertNotIn("-pix_fmt", c)

    def test_other_encoders_unchanged(self):
        with mock.patch.object(encoders, "_working", ["qsv"]):
            args = encoders.video_args(encoders.choose("auto"), "bwdif")
        self.assertEqual(args[:2], ["-vf", "bwdif"])
        self.assertEqual(args[-2:], ["-pix_fmt", "nv12"])

    def test_captions_use_the_cpu(self):
        # h264_vaapi's caption support isn't checked, so captions on converts on the CPU
        self.assertFalse(encoders.keeps_captions(self.enc()))


if __name__ == "__main__":
    unittest.main()
