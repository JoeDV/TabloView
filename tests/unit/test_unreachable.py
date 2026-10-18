import asyncio
import unittest
from unittest import mock

import httpx

from app.tablo_client import tablo_manager
from tablo_api.models import TabloDevice


class UnreachableTests(unittest.TestCase):
    """The Tablo sometimes refuses connections for a minute; TabloView should notice and recover."""

    def setUp(self):
        self.up = False

        def handler(request):
            if not self.up:
                raise httpx.ConnectError("All connection attempts failed", request=request)
            return httpx.Response(200, json={"ok": True})

        device = mock.MagicMock(spec=TabloDevice)
        device.local_url = "http://tablo.test:8887"
        patches = [
            mock.patch.object(tablo_manager, "device", device),
            mock.patch.object(tablo_manager, "_http", httpx.AsyncClient(transport=httpx.MockTransport(handler))),
            mock.patch("app.tablo_client.TabloAuth.make_device_auth", return_value=("auth", "date")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        tablo_manager.unreachable_since = None
        self.addCleanup(setattr, tablo_manager, "unreachable_since", None)

    def test_refused_connection_marks_unreachable_until_it_answers(self):
        with self.assertRaises(httpx.ConnectError):
            asyncio.run(tablo_manager.request_local("GET", "/server/info"))
        self.assertTrue(tablo_manager.tablo_unreachable)
        self.up = True
        asyncio.run(tablo_manager.request_local("GET", "/server/info"))
        self.assertFalse(tablo_manager.tablo_unreachable)


if __name__ == "__main__":
    unittest.main()
