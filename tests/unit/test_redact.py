try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from tablo_api.models import TabloDevice

from app import redact
from app.main import app
from app.tablo_client import tablo_manager

LIGHTHOUSE = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"  # made up
ACCOUNT = "acct-made-up-0123456789"
DEVICE = TabloDevice(sid="SID_TEST", name="Test", local_url="http://192.168.1.50:8887",
                     lighthouse_token=LIGHTHOUSE, account_token=ACCOUNT,
                     client_id="00000000-0000-0000-0000-000000000000")
HDR = {"X-TabloView": "1"}


class RedactTests(unittest.TestCase):
    """The log gets pasted into forum posts: no sign-in tokens or the account's email in it (an error
    repeating a cloud address put the Lighthouse token there)."""

    def setUp(self):
        for p in (mock.patch.object(tablo_manager, "device", DEVICE), mock.patch.object(tablo_manager, "devices", [DEVICE]),
                  mock.patch.object(tablo_manager, "email", "someone@example.com")):
            p.start()
            self.addCleanup(p.stop)

    def test_tokens_email_account_paths_and_bearer_values_are_hidden(self):
        text = (f"401 Client Error for url: https://lighthousetv.ewscloud.com/api/v2/account/{LIGHTHOUSE}/guide/grid/?day=1 "
                f"Authorization: Bearer {ACCOUNT} by someone@example.com; other account /api/v2/account/abc123/x Bearer zzz.yyy")
        out = redact.scrub(text)
        for secret in (LIGHTHOUSE, ACCOUNT, "someone@example.com", "abc123", "zzz.yyy"):
            self.assertNotIn(secret, out)
        self.assertIn("/api/v2/account/<hidden>/guide/grid/", out)

    def test_printed_text_is_scrubbed_once_installed(self):
        stream = io.StringIO()
        wrapped = redact._Scrubbed(stream)
        print(f"[Streaming] failed: https://x/api/v2/account/{LIGHTHOUSE}/guide", file=wrapped)
        self.assertNotIn(LIGHTHOUSE, stream.getvalue())
        self.assertEqual(wrapped.getvalue(), stream.getvalue())  # anything else goes to the real stream

    def test_diagnostics_hide_sign_in_details_and_are_for_this_pc_only(self):
        logs = Path(tempfile.mkdtemp())
        (logs / "tabloview.log").write_text(
            f"[Startup] hello\n[LiveTV] Error: https://x/api/v2/account/{LIGHTHOUSE}/guide for someone@example.com\n"
            f"Saved to {Path.home()}\\Downloads\\TabloView\n", encoding="utf-8")
        with mock.patch("app.config.LOG_DIR", logs), mock.patch("app.routes.system.get_sync_meta", return_value=None), \
             mock.patch("app.encoders.detect", return_value=[]):
            pc = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
            text = pc.get("/api/system/diagnostics", headers=HDR).json()["text"]
            phone = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))
            with mock.patch("app.lanauth.blocked", return_value=None):  # signed in with the PIN
                self.assertEqual(phone.get("/api/system/diagnostics", headers=HDR).status_code, 403)
        self.assertIn("[Startup] hello", text)
        self.assertIn("Tablo: Test at http://192.168.1.50:8887", text)
        for secret in (LIGHTHOUSE, ACCOUNT, "someone@example.com", str(Path.home())):
            self.assertNotIn(secret, text)
        self.assertIn("%USERPROFILE%\\Downloads", text)


if __name__ == "__main__":
    unittest.main()
