import json
import unittest
from unittest import mock

from app.routes import live
from app.tablo_client import tablo_manager


class Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class ChannelBatchTests(unittest.IsolatedAsyncioTestCase):
    """The Live TV guide reads the Tablo's channels in batches of 50, not one request per channel."""

    async def test_many_channels_take_a_few_batch_requests(self):
        paths = [f"/guide/channels/{n}" for n in range(120)]
        calls = []

        async def fake(method, path, body=""):
            calls.append((method, path))
            if path == "/guide/channels":
                return Resp(paths)
            asked = json.loads(body)
            return Resp({p: {"object_id": int(p.rsplit("/", 1)[1]),
                             "channel": {"channel_identifier": f"S{p.rsplit('/', 1)[1]}", "call_sign": "WXYZ"}}
                         for p in asked})

        with mock.patch.object(tablo_manager, "request_local", new=fake):
            got = await live.fetch_local_ota_map()
        self.assertEqual(calls, [("GET", "/guide/channels")] + [("POST", "/batch")] * 3)
        self.assertEqual(len(got), 120)
        self.assertEqual(got["S7"]["_path"], "/guide/channels/7")

    async def test_a_rejected_batch_leaves_those_channels_out(self):
        async def fake(method, path, body=""):
            return Resp(["/guide/channels/1"]) if path == "/guide/channels" else Resp(None, status=500)

        with mock.patch.object(tablo_manager, "request_local", new=fake):
            self.assertEqual(await live.fetch_local_ota_map(), {})


if __name__ == "__main__":
    unittest.main()
