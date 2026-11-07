try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app import encoders
from app.transcode import transcode_manager


class CaptionEncoderTests(unittest.TestCase):
    """AMD's and Apple's encoders drop the broadcast's captions (the user's AMD mini PC: none in The
    Amazing Race). With captions on, that stream is converted on the CPU; without, the chip as before."""

    def plan(self, chip, captions, passthrough=False, quality="auto", away=False, away_picture="full"):
        settings = {"video_quality": quality, "smooth_motion": True, "away_picture": away_picture}
        with mock.patch("app.transcode.load_settings", return_value=settings), \
                mock.patch.object(encoders, "detect", return_value=[chip] if chip else []):
            return transcode_manager._video_plan(passthrough, away, captions)

    def test_which_encoders_keep_captions(self):
        for name in ("qsv", "nvenc", "cpu", "fastest"):
            self.assertTrue(encoders.keeps_captions({"name": name}), name)
        for name in ("amf", "videotoolbox"):
            self.assertFalse(encoders.keeps_captions({"name": name}), name)
        self.assertTrue(encoders.keeps_captions(None))  # copied video keeps whatever it carries

    def test_amd_with_captions_uses_the_cpu(self):
        plan = self.plan("amf", captions=True)
        self.assertEqual(plan["encoder"]["name"], "cpu")
        self.assertFalse(plan["smooth"])  # 60 fps would double the CPU's work
        self.assertTrue(plan.get("for_captions"))

    def test_amd_without_captions_stays_on_the_chip(self):
        plan = self.plan("amf", captions=False)
        self.assertEqual(plan["encoder"]["name"], "amf")
        self.assertTrue(plan["smooth"])

    def test_chips_that_keep_captions_are_unchanged(self):
        for chip in ("qsv", "nvenc", None):
            self.assertEqual(self.plan(chip, captions=True)["encoder"]["name"], chip or "cpu")
        self.assertIsNone(self.plan("amf", captions=True, passthrough=True)["encoder"])  # streaming: copied

    def test_away_picture_still_smaller(self):
        plan = self.plan("amf", captions=True, away=True, away_picture="480")
        self.assertEqual(plan["encoder"]["name"], "cpu")
        self.assertEqual(plan["size"], (480, 1200))


if __name__ == "__main__":
    unittest.main()
