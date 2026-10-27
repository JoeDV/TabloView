try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import json
import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from tablo_api.models import TabloDevice

from app.main import app
from app.tablo_client import tablo_manager

LIGHTHOUSE = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"  # made up
ACCOUNT = "acct-token-0123456789abcdef"
DEVICE = TabloDevice(sid="SID_TEST", name="Test", local_url="http://192.168.1.50:8887",
                     lighthouse_token=LIGHTHOUSE, account_token=ACCOUNT,
                     client_id="9d976442-9ce4-4f16-947d-850f1beb30b6")


class InspectorPrivacyTests(unittest.TestCase):
    """The API inspector's output gets pasted into forum posts: no sign-in tokens in it (a user's
    showed their account's Lighthouse token in the cloud check's path)."""

    def run_inspector(self, cloud):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        local = mock.AsyncMock(return_value=httpx.Response(200, json=[]))
        with mock.patch.object(tablo_manager, "device", DEVICE), \
             mock.patch.object(tablo_manager, "request_local", new=local), \
             mock.patch.object(tablo_manager._http, "get", new=cloud):
            return client.get("/api/debug/endpoints").text

    def test_tokens_are_masked_when_the_cloud_answers(self):
        out = self.run_inspector(mock.AsyncMock(return_value=httpx.Response(200, json=[{"identifier": "S1"}])))
        self.assertNotIn(LIGHTHOUSE, out)
        self.assertNotIn(ACCOUNT, out)
        self.assertNotIn(DEVICE.client_id, out)
        cloud = [p for p in json.loads(out)["probes"] if p["target"] == "cloud"][0]
        self.assertEqual(cloud["path"], "/api/v2/account/0123…cdef/guide/channels/")
        self.assertTrue(cloud["success"])

    def test_says_which_tabloview_sent_it(self):
        from app.config import APP_VERSION
        out = json.loads(self.run_inspector(mock.AsyncMock(return_value=httpx.Response(200, json=[]))))
        self.assertEqual(out["tabloview"]["version"], APP_VERSION)
        self.assertEqual(out["tabloview"]["edition"], "source")
        self.assertTrue(out["tabloview"]["os"])

    def test_tokens_are_masked_in_errors_that_repeat_the_url(self):
        url = f"https://lighthousetv.ewscloud.com/api/v2/account/{LIGHTHOUSE}/guide/channels/"
        out = self.run_inspector(mock.AsyncMock(side_effect=httpx.ConnectError(f"Couldn't reach {url} with {ACCOUNT}")))
        self.assertNotIn(LIGHTHOUSE, out)
        self.assertNotIn(ACCOUNT, out)
        self.assertIn("0123…cdef", out)


if __name__ == "__main__":
    unittest.main()
