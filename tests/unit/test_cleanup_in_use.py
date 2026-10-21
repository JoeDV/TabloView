import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import transcode


class StartupCleanupTests(unittest.TestCase):
    """Start-up cleanup leaves a session folder alone while it's being written (another TabloView
    process is playing it): wiping one deleted a live stream's rewind."""

    def test_only_old_folders_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, live = root / "old_session", root / "live_session"
            for d in (old, live):
                d.mkdir()
                (d / "00001.ts").write_bytes(b"x")
            hour_ago = time.time() - 3600
            os.utime(old / "00001.ts", (hour_ago, hour_ago))
            with mock.patch.object(transcode, "TRANSCODE_DIR", root):
                transcode.TranscodeManager.cleanup_stale_transcodes(mock.Mock(_in_use=transcode.TranscodeManager._in_use))
            self.assertFalse(old.exists())
            self.assertTrue((live / "00001.ts").exists())


if __name__ == "__main__":
    unittest.main()
