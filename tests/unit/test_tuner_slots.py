try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest
from unittest import mock

from app.routes import live

CHANNELS = {
    "S1_004_01": {"_path": "/guide/channels/100", "major": 4, "minor": 1, "call_sign": "WNBC", "network": "NBC"},
    "S2_002_01": {"_path": "/guide/channels/200", "major": 2, "minor": 1, "call_sign": "WCBS", "network": "CBS"},
}


class TunerSlotTests(unittest.TestCase):
    """The header's tuner list: what each antenna tuner is doing (a user's idea: 'Tuner 1: Recording
    NBC Nightly News (4.1), Tuner 2: Live TV CBS (2.1), Tuners 3 & 4: Free')."""

    def slots(self, ota, ours=(), closed=()):
        on_now = {"S1_004_01": {"show_title": "NBC Nightly News", "episode_title": ""}}
        with mock.patch.object(live, "airing_on_now", side_effect=lambda ident: on_now.get(ident)):
            return live.tuner_slots(ota, CHANNELS, set(ours), set(closed))

    def test_the_users_example(self):
        s = self.slots([
            {"in_use": True, "recording": True, "channel": "/guide/channels/100"},
            {"in_use": True, "recording": False, "channel": "/guide/channels/200"},
            {"in_use": False}, {"in_use": False},
        ], ours={"S2_002_01"})
        self.assertEqual([x["state"] for x in s], ["recording", "watching", "free", "free"])
        self.assertEqual(s[0]["channel"]["number"], "4.1")
        self.assertEqual(s[0]["on_now"]["show_title"], "NBC Nightly News")
        self.assertEqual(s[1]["channel"]["call_sign"], "WCBS")
        self.assertTrue(s[1]["tabloview"])

    def test_live_tv_in_another_app(self):
        s = self.slots([{"in_use": True, "recording": False, "channel": "/guide/channels/200"}])
        self.assertFalse(s[0]["tabloview"])

    def test_a_tuner_still_held_after_live_tv_closed(self):
        s = self.slots([{"in_use": True, "recording": False, "channel": None}])
        self.assertEqual(s[0]["state"], "releasing")
        self.assertNotIn("channel", s[0])

    def test_a_channel_tabloview_just_closed_isnt_another_app(self):
        # Cancelling the antenna check: the Tablo kept 13.1 on the tuner for a while after
        s = self.slots([{"in_use": True, "recording": False, "channel": "/guide/channels/100"}], closed={"S1_004_01"})
        self.assertTrue(s[0]["closing"])
        self.assertFalse(s[0]["tabloview"])

    def test_the_tuners_own_channel_id_is_used(self):
        s = self.slots([{"in_use": True, "recording": False, "channel": "/guide/channels/elsewhere",
                         "channel_identifier": "S2_002_01"}], ours={"S2_002_01"})
        self.assertEqual(s[0]["channel"]["number"], "2.1")
        self.assertTrue(s[0]["tabloview"])

    def test_a_channel_the_list_doesnt_know_still_shows_its_state(self):
        s = self.slots([{"in_use": True, "recording": True, "channel": "/guide/channels/999"}])
        self.assertEqual(s[0]["state"], "recording")
        self.assertNotIn("channel", s[0])



class RecordingNowTests(unittest.TestCase):
    """Live TV's REC badge: streaming channels too (a streaming recording didn't show)."""

    def test_streaming_slots_are_found_by_their_channel_id(self):
        import asyncio
        import httpx
        tuners = [{"in_use": True, "recording": "/recordings/series/episodes/1", "channel": "/guide/channels/100",
                   "channel_identifier": "S1_004_01"},
                  {"in_use": True, "recording": "/recordings/series/episodes/2", "channel": "/guide/channels/251",
                   "channel_identifier": "S122912_503_01"},  # ION, not in the antenna channel list
                  {"in_use": True, "recording": None, "channel": "/guide/channels/200", "channel_identifier": "S2_002_01"}]
        with mock.patch.object(live.tablo_manager, "request_local", new=mock.AsyncMock(return_value=httpx.Response(200, json=tuners))):
            found = asyncio.run(live.recording_channel_identifiers(CHANNELS))
        self.assertEqual(found, {"S1_004_01", "S122912_503_01"})


if __name__ == "__main__":
    unittest.main()
