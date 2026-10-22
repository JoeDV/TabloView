try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import subprocess
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.routes import system

HDR = {"X-TabloView": "1"}


class PickFolderTests(unittest.TestCase):
    """Save exports to → Change…: a picker that fails must say so, not look like Cancel."""

    def pick(self, stdout=b"", stderr=b"", returncode=0, error=None):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        done = subprocess.CompletedProcess([], returncode, stdout, stderr)
        run = mock.Mock(side_effect=error) if error else mock.Mock(return_value=done)
        with mock.patch.object(system.sys, "platform", "win32"), mock.patch.object(system.subprocess, "run", new=run), \
                mock.patch.object(system.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            return client.post("/api/system/pick_folder", headers=HDR)

    def test_a_chosen_folder(self):
        r = self.pick(stdout="PICKED:D:\\Videos\\Tablo\r\n".encode())
        self.assertEqual(r.json(), {"path": "D:\\Videos\\Tablo"})

    def test_cancel(self):
        self.assertEqual(self.pick(stdout=b"CANCELLED\r\n").json(), {"path": None})

    def test_a_blocked_powershell_is_an_error(self):
        # Used to return no path, the same as Cancel, so nothing happened at all
        r = self.pick(stderr=b"Add-Type : Cannot add type.", returncode=1)
        self.assertEqual(r.status_code, 500)

    def test_no_powershell_is_an_error(self):
        self.assertEqual(self.pick(error=FileNotFoundError("powershell")).status_code, 500)


if __name__ == "__main__":
    unittest.main()
