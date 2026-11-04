try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from pathlib import Path
from unittest import mock

from app import encoders
from app.netcheck import away_from_home
from app.transcode import transcode_manager


class AwayFromHomeTests(unittest.TestCase):
    """Settings → Playback → Away from home: a smaller picture over Tailscale, only when asked for
    (the user: "if I want full HD I should get it")."""

    def test_who_is_away(self):
        for host in ("100.77.38.52", "fd7a:115c:a1e0::1", "8.8.8.8", "::ffff:100.101.1.2"):
            self.assertTrue(away_from_home(host), host)
        for host in ("127.0.0.1", "::1", "192.168.1.40", "10.0.0.5", "172.20.1.1", "fe80::1", "testclient", None):
            self.assertFalse(away_from_home(host), host)

    def plan(self, away_picture, away=True, passthrough=False):
        with mock.patch("app.transcode.load_settings", return_value={"away_picture": away_picture, "smooth_motion": True}), \
                mock.patch.object(encoders, "detect", return_value=[]):
            return transcode_manager._video_plan(passthrough, away)

    def test_full_picture_unless_asked(self):
        self.assertIsNone(self.plan("full")["size"])
        self.assertIsNone(self.plan("480", away=False)["size"])
        self.assertTrue(self.plan("full")["smooth"])
        self.assertIsNone(self.plan("full", passthrough=True)["encoder"])  # streaming channels: copied as before

    def test_smaller_picture_away(self):
        plan = self.plan("480")
        self.assertEqual(plan["size"], (480, 1200))
        self.assertFalse(plan["smooth"])
        self.assertIsNotNone(self.plan("720", passthrough=True)["encoder"])  # converted, to make it smaller
        cmd = transcode_manager._build_cmd("http://tablo/p.m3u8", 0, False, plan, Path("s"))
        vf = cmd[cmd.index("-vf") + 1]
        self.assertTrue(vf.endswith(",scale=-2:'min(480,ih)'"))
        self.assertEqual(cmd[cmd.index("-maxrate") + 1], "1800k")

    def test_every_encoder_gets_a_ceiling(self):
        for name in ("qsv", "nvenc", "amf", "videotoolbox", "cpu", "fastest"):
            args = encoders.capped({"name": name, "args": [], "pix_fmt": "yuv420p"}, 3000)["args"]
            self.assertIn("-maxrate", args, name)
            self.assertNotIn("-global_quality", args)
            self.assertNotIn("-cq", args)


if __name__ == "__main__":
    unittest.main()
