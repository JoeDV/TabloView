try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import transcode
from app.transcode import StreamSession, TranscodeManager


class StuckFFmpeg:
    """Running, but writing nothing: FFmpeg waiting on a Tablo that stopped sending."""

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class FinishedFFmpeg(StuckFFmpeg):
    def __init__(self):
        self.returncode = 0


class StreamStallTests(unittest.TestCase):
    """A stuck FFmpeg is restarted on the same Tablo session, without waiting for it to exit
    (it doesn't: it waits on the Tablo, and live TV used to stop with "Live TV stopped responding")."""

    def test_a_stuck_live_stream_is_restarted(self):
        real_sleep = asyncio.sleep
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            (session_dir / "playlist.m3u8").write_text("#EXTM3U\n#EXTINF:3.0,\n00001.ts\n", encoding="utf-8")
            m = TranscodeManager.__new__(TranscodeManager)
            m.sessions, m.smooth_live_too_slow = {}, False
            sess = StreamSession("abc", "http://tablo/live.m3u8")
            m.sessions["abc"] = sess
            sess.proc = StuckFFmpeg()
            restarted = []

            def popen(cmd, **kwargs):
                restarted.append(cmd)
                return FinishedFFmpeg()  # the restart works and runs to the end

            plan = {"encoder": None, "smooth": False, "quality": "auto"}
            with mock.patch.object(transcode, "STREAM_STALL_SECONDS", 0.05), \
                 mock.patch.object(transcode.asyncio, "sleep", new=lambda s: real_sleep(0.02)), \
                 mock.patch.object(transcode.subprocess, "Popen", side_effect=popen), \
                 mock.patch.object(transcode.childproc, "tie_to_app"), \
                 mock.patch.object(transcode, "run_at_full_speed"):
                asyncio.run(m._supervise(sess, "http://tablo/live.m3u8", 0, True, plan, session_dir))
            self.assertEqual(len(restarted), 1)
            self.assertIn("http://tablo/live.m3u8", restarted[0])  # the same Tablo session, no new tune
            self.assertIn("independent_segments+append_list+discont_start", " ".join(restarted[0]))


if __name__ == "__main__":
    unittest.main()
