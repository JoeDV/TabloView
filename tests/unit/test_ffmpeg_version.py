try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app.routes import system


class FfmpegVersionTests(unittest.TestCase):
    """Help's credits name the FFmpeg in use, so its exact source can be found."""

    def setUp(self):
        system._ffmpeg_version.clear()
        self.addCleanup(system._ffmpeg_version.clear)

    def test_the_version_as_ffmpeg_names_itself(self):
        out = "ffmpeg version 9.0.1-essentials_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers\nbuilt with gcc\n"
        with mock.patch.object(system.subprocess, "run", return_value=mock.Mock(stdout=out)) as run:
            self.assertEqual(system.ffmpeg_version(), "9.0.1-essentials_build-www.gyan.dev")
            system.ffmpeg_version()
        run.assert_called_once()  # asked once

    def test_none_when_ffmpeg_cant_be_run(self):
        with mock.patch.object(system.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(system.ffmpeg_version())


if __name__ == "__main__":
    unittest.main()
