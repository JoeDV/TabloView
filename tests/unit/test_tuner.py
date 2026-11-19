import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from fastapi.testclient import TestClient

from app import tuner

CHANS = [
    {"number": "6.1", "name": "WRTV", "call_sign": "WRTVDT1", "network": "ABC", "logo": "https://x/abc.png",
     "id": "S1_006_01", "hd": True},
    {"number": "13.2", "name": "Me & You", "call_sign": "WTHRDT2", "network": "", "logo": None, "id": "S1_013_02", "hd": False},
]


class TunerTests(unittest.TestCase):
    """TabloView as an HDHomeRun for Plex, Jellyfin, Emby and Channels DVR."""

    def setUp(self):
        for p in (mock.patch.object(tuner, "lineup", new=mock.AsyncMock(return_value=CHANS)),
                  mock.patch.object(tuner, "tuner_count", new=mock.AsyncMock(return_value=4)),
                  mock.patch.object(tuner, "device_id", return_value="1A2B3C4D")):
            p.start()
            self.addCleanup(p.stop)

    def client(self, host="192.168.1.20"):
        return TestClient(tuner.app, base_url="http://192.168.1.69:5004", client=(host, 50000))

    def test_discover_names_this_address_and_the_tablos_tuners(self):
        d = self.client().get("/discover.json").json()
        self.assertEqual(d["BaseURL"], "http://192.168.1.69:5004")
        self.assertEqual(d["LineupURL"], "http://192.168.1.69:5004/lineup.json")
        self.assertEqual((d["TunerCount"], d["DeviceID"]), (4, "1A2B3C4D"))

    def test_lineup_has_a_stream_per_channel(self):
        rows = self.client().get("/lineup.json").json()
        self.assertEqual(rows[0], {"GuideNumber": "6.1", "GuideName": "WRTV", "URL": "http://192.168.1.69:5004/auto/v6.1", "HD": 1})
        self.assertNotIn("HD", rows[1])

    def test_m3u_matches_the_guide(self):
        text = self.client().get("/lineup.m3u").text
        self.assertTrue(text.startswith('#EXTM3U url-tvg="http://192.168.1.69:5004/xmltv.xml"'))
        self.assertIn('tvg-id="13.2"', text)
        self.assertIn("tvg-name=\"Me & You\"", text)
        self.assertIn("http://192.168.1.69:5004/auto/v13.2", text)

    def test_away_from_home_is_refused(self):
        # Those apps can't type the PIN, so nothing outside the home network gets an answer
        self.assertEqual(self.client("8.8.8.8").get("/discover.json").status_code, 403)
        self.assertEqual(self.client("100.101.102.103").get("/lineup.json").status_code, 403)  # Tailscale
        self.assertEqual(self.client("127.0.0.1").get("/discover.json").status_code, 200)

    def test_unknown_channel(self):
        self.assertEqual(self.client().get("/auto/v99.9").status_code, 404)

    def test_stream_is_copied_not_converted(self):
        cmd = tuner.stream_cmd("http://tablo/pl.m3u8")
        self.assertEqual(cmd[cmd.index("-c") + 1], "copy")
        self.assertEqual(cmd[cmd.index("-f") + 1], "mpegts")
        self.assertEqual(cmd[-1], "pipe:1")

    def test_guide_is_xmltv(self):
        airings = [
            {"show_title": "Jeopardy!", "episode_title": "Tournament <1>", "season_number": 42, "episode_number": 50,
             "air_datetime": "2026-11-19T23:30Z", "duration": 1800, "channel_call_sign": "WRTVDT1",
             "channel_identifier": "S1_006_01", "is_new": 1, "is_premiere": 0, "description": "Quiz & more", "genres": ["Game show"],
             "cover_url": "/api/images/23871"},
            # matched by call sign when the identifier isn't known
            {"show_title": "News", "episode_title": None, "season_number": 0, "episode_number": 0,
             "air_datetime": "2026-11-20T00:00Z", "duration": 3600, "channel_call_sign": "wthrdt2",
             "channel_identifier": None, "is_new": 0, "is_premiere": 0, "description": None, "genres": []},
            {"show_title": "Elsewhere", "air_datetime": "2026-11-20T00:00Z", "duration": 60, "channel_identifier": "X"},
        ]
        root = ET.fromstring(tuner.guide_xml(CHANS, airings, "http://192.168.1.69:5004"))
        self.assertEqual([c.get("id") for c in root.findall("channel")], ["6.1", "13.2"])
        # Plex puts the number before the first name: that one is the plain name
        self.assertEqual(root.find("channel").findtext("display-name"), "WRTV")
        progs = root.findall("programme")
        self.assertEqual(len(progs), 2)
        p = progs[0]
        self.assertEqual((p.get("start"), p.get("stop"), p.get("channel")), ("20261119233000 +0000", "20261120000000 +0000", "6.1"))
        self.assertEqual(p.findtext("sub-title"), "Tournament <1>")
        self.assertEqual(p.findtext("episode-num[@system='xmltv_ns']"), "41.49.")
        self.assertEqual(p.findtext("episode-num[@system='onscreen']"), "S42E50")
        self.assertIsNotNone(p.find("new"))
        # The show's poster, from the Tablo through the tuner's own address (Plex showed blank cards)
        self.assertEqual(p.find("icon").get("src"), "http://192.168.1.69:5004/images/23871")
        self.assertIsNone(progs[1].find("icon"))
        self.assertEqual(progs[1].get("channel"), "13.2")
        self.assertIsNotNone(progs[1].find("previously-shown"))


if __name__ == "__main__":
    unittest.main()
