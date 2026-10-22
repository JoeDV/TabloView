try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.routes import system

HDR = {"X-TabloView": "1"}


class StopTests(unittest.TestCase):
    """Stop TabloView on the Device page: copies run from a start script have no tray icon to quit from."""

    def post(self, client_host, packaged=False):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=(client_host, 50000))
        stop = mock.Mock()
        with mock.patch.object(system, "request_stop", new=stop), mock.patch.object(system, "IS_PACKAGED", packaged):
            r = client.post("/api/system/stop", headers=HDR)
        return r, stop

    def test_stops_from_this_computer(self):
        r, stop = self.post("127.0.0.1")
        self.assertEqual(r.json(), {"stopping": True})
        stop.assert_called_once()

    def test_not_from_another_device(self):
        with mock.patch("app.lanauth.blocked", return_value=None):  # signed in with the PIN
            r, stop = self.post("192.168.1.50")
        self.assertEqual(r.status_code, 403)
        stop.assert_not_called()

    def test_the_installed_app_quits_from_the_tray(self):
        r, stop = self.post("127.0.0.1", packaged=True)
        self.assertEqual(r.status_code, 400)
        stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
