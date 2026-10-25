try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import json
import unittest
from unittest import mock

import httpx

from app.routes import live
from app.tablo_client import tablo_manager

STREAMING = {"object_id": 247, "path": "/guide/channels/247", "channel": {
    "call_sign": "Scripps News", "major": 500, "minor": 1, "favourite": True,
    "resolution": "hd_1080", "channel_identifier": "S120010_500_01", "logos": []}}


class FavouriteChannelTests(unittest.TestCase):
    """Favourites set in the Tablo's apps: a user had no Favorites filter in Live TV. Tablo's apps keep
    them in the account's profile; the Tablo's own per-channel flag (read with ?lh for streaming
    channels too) is still honoured for older apps."""

    def test_a_favourite_streaming_channel_is_seen(self):
        asked = []

        async def request_local(method, path, body=""):
            asked.append(path)
            if path == "/guide/channels?lh":
                return httpx.Response(200, json=["/guide/channels/247"])
            if path == "/batch?lh":
                return httpx.Response(200, json={p: STREAMING for p in json.loads(body)})
            return httpx.Response(404, json={})

        with mock.patch.object(tablo_manager, "request_local", side_effect=request_local):
            found = asyncio.run(live.fetch_local_ota_map())
        self.assertEqual(asked, ["/guide/channels?lh", "/batch?lh"])
        self.assertTrue(found["S120010_500_01"]["favourite"])

        ch = mock.Mock(identifier="S120010_500_01", call_sign="Scripps News", major=500, minor=1, network="", kind="ott")
        self.assertTrue(live.base_channel_dict(ch, {}, found)["favorite"])

    def test_favourites_from_the_account_profile(self):
        # Where Tablo's apps keep them now: the account's profile, by channel identifier
        account = {"profiles": [{"name": "Profile 1", "preferences": {"favorite_channels": ["S19593_013_01"]}},
                                {"name": "Kids", "preferences": {"favorite_channels": ["S1_002_01"]}}]}
        client = mock.Mock()
        client._session.get.return_value = mock.Mock(json=lambda: account, raise_for_status=lambda: None)
        with mock.patch.dict(live._favourites, {"at": 0.0, "ids": set()}):
            ids = asyncio.run(live.fetch_favourites(client))
        self.assertEqual(ids, {"S19593_013_01"})  # the first profile, the one TabloView signs in as
        ch = mock.Mock(identifier="S19593_013_01", call_sign="WTHR", major=13, minor=1, network="NBC", kind="ota")
        self.assertTrue(live.base_channel_dict(ch, {}, {}, ids)["favorite"])
        ch.identifier = "S21102_006_01"
        self.assertFalse(live.base_channel_dict(ch, {}, {}, ids)["favorite"])


if __name__ == "__main__":
    unittest.main()
