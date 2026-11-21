import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from fastapi.testclient import TestClient

from app import dlna, tuner

CHANS = [
    {"number": "6.1", "name": "WRTV", "call_sign": "WRTVDT1", "network": "ABC", "logo": "https://x/abc.png",
     "id": "S1_006_01", "hd": True},
    {"number": "13.2", "name": "Me & You", "call_sign": "WTHRDT2", "network": "", "logo": None, "id": "S1_013_02", "hd": False},
]
SHOWS = [{"id": "survivor", "title": "Survivor", "episode_count": 2, "cover_url": "/api/images/50807?v=2"}]
EPISODES = {"survivor": [
    {"id": "ep_10", "show_id": "survivor", "path": "/recordings/series/episodes/10", "season_number": 51, "episode_number": 10,
     "title": "Sorting Hogs", "air_date": "2026-11-25T01:00Z", "duration": 3600, "recording_state": "recording"},
    {"id": "ep_9", "show_id": "survivor", "path": "/recordings/series/episodes/9", "season_number": 51, "episode_number": 9,
     "title": "The Tribe Has Spoken", "air_date": "2026-11-18T01:00Z", "duration": 3600, "actual_duration": 3845,
     "recording_state": "finished"},
]}
NS = {"d": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/", "dc": "http://purl.org/dc/elements/1.1/",
      "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/"}


def browse_body(object_id, flag="BrowseDirectChildren", start=0, count=0):
    return (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<u:Browse xmlns:u="{dlna.CDS}"><ObjectID>{object_id}</ObjectID><BrowseFlag>{flag}</BrowseFlag>'
            f"<Filter>*</Filter><StartingIndex>{start}</StartingIndex><RequestedCount>{count}</RequestedCount>"
            f"<SortCriteria></SortCriteria></u:Browse></s:Body></s:Envelope>")


class DlnaTests(unittest.TestCase):
    """The Tablo's channels as a DLNA media server, for Roku Media Player, VLC, Kodi and smart TVs."""

    def setUp(self):
        dlna._now.update(at=0.0, titles={})
        airings = [{"show_title": "Jeopardy!", "channel_identifier": "S1_006_01"}]
        for p in (mock.patch.object(tuner, "lineup", new=mock.AsyncMock(return_value=CHANS)),
                  mock.patch.object(tuner, "device_id", return_value="1A2B3C4D"),
                  mock.patch.object(tuner, "guide_airings", return_value=airings),
                  mock.patch.object(dlna, "_rec_shows", return_value=SHOWS),
                  mock.patch.object(dlna, "_rec_episodes", side_effect=lambda sid: EPISODES.get(sid, []))):
            p.start()
            self.addCleanup(p.stop)

    def client(self, host="192.168.1.20"):
        return TestClient(tuner.app, base_url="http://192.168.1.69:5004", client=(host, 50000))

    def browse(self, *args, **kw):
        r = self.client().post("/dlna/control/cds", content=browse_body(*args, **kw),
                               headers={"SOAPACTION": f'"{dlna.CDS}#Browse"'})
        return r

    def result(self, r):
        self.assertEqual(r.status_code, 200)
        env = ET.fromstring(r.content)
        resp = next(el for el in env.iter() if el.tag.endswith("BrowseResponse"))
        vals = {el.tag: el.text for el in resp}
        return ET.fromstring(vals["Result"]), int(vals["NumberReturned"]), int(vals["TotalMatches"])

    def test_device_names_both_services(self):
        root = ET.fromstring(self.client().get("/dlna/device.xml").content)
        ns = {"u": "urn:schemas-upnp-org:device-1-0"}
        self.assertEqual(root.findtext("u:device/u:deviceType", namespaces=ns), dlna.DEVICE)
        self.assertEqual(root.findtext("u:device/u:friendlyName", namespaces=ns), "TabloView")
        self.assertEqual(root.findtext("u:device/u:UDN", namespaces=ns), dlna.udn())
        controls = [s.findtext("u:controlURL", namespaces=ns) for s in root.iterfind("u:device/u:serviceList/u:service", ns)]
        self.assertEqual(controls, ["/dlna/control/cds", "/dlna/control/cms"])
        for url in ("/dlna/cds.xml", "/dlna/cms.xml", "/dlna/icon.png"):
            self.assertEqual(self.client().get(url).status_code, 200, url)
        ET.fromstring(self.client().get("/dlna/cds.xml").content)

    def test_root_has_live_tv_and_recordings(self):
        didl, n, total = self.result(self.browse("0"))
        self.assertEqual((n, total), (2, 2))
        got = [(c.get("id"), c.get("childCount"), c.findtext("dc:title", namespaces=NS)) for c in didl.findall("d:container", NS)]
        self.assertEqual(got, [("live", "2", "Live TV"), ("rec", "1", "Recordings")])

    def test_recordings_by_show_newest_first(self):
        didl, n, _ = self.result(self.browse("rec"))
        folder = didl.find("d:container", NS)
        self.assertEqual((folder.get("id"), folder.findtext("dc:title", namespaces=NS)), ("rs-survivor", "Survivor"))
        # The Tablo's picture, through the tuner's port (TabloView's own wants the PIN)
        self.assertEqual(folder.findtext("upnp:albumArtURI", namespaces=NS), "http://192.168.1.69:5004/images/50807")
        didl, n, total = self.result(self.browse("rs-survivor"))
        items = didl.findall("d:item", NS)
        self.assertEqual([i.findtext("dc:title", namespaces=NS) for i in items],
                         ["S51 E10 · Sorting Hogs (recording now)", "S51 E9 · The Tribe Has Spoken"])
        res = items[1].find("d:res", NS)
        self.assertEqual(res.text, "http://192.168.1.69:5004/dlna/rec/ep_9.ts")
        self.assertEqual(res.get("duration"), "1:04:05.000")
        self.assertIn("DLNA.ORG_OP=10", res.get("protocolInfo"))  # seeking by time
        self.assertEqual(self.browse("rs-nothing").status_code, 500)  # unknown: a 701 fault

    def test_time_seek_header(self):
        self.assertEqual(dlna.seek_start("npt=1234.5-"), 1234.5)
        self.assertEqual(dlna.seek_start("npt=0:20:34.5-0:30:00"), 1234.5)
        self.assertEqual(dlna.seek_start(None), 0)
        self.assertEqual(dlna.seek_start("bytes=0-"), 0)

    def test_head_answers_without_asking_the_tablo(self):
        with mock.patch("app.database.get_episode_by_id", return_value=EPISODES["survivor"][1]),                 mock.patch("app.tablo_client.tablo_manager.get_airing_watch_url") as watch:
            r = self.client().head("/dlna/rec/ep_9.ts", headers={"TimeSeekRange.dlna.org": "npt=600-"})
        watch.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["timeseekrange.dlna.org"], "npt=600.000-3845.000/3845.000")
        with mock.patch("app.database.get_episode_by_id", return_value=None):
            self.assertEqual(self.client().head("/dlna/rec/nope.ts").status_code, 404)

    def test_recording_stream_command(self):
        cmd = tuner.stream_cmd("http://127.0.0.1:7070/relay/p.m3u8", {"name": "cpu", "args": ["-c:v", "libx264"], "pix_fmt": "yuv420p"},
                               start=600, recording=True)
        self.assertEqual(cmd[cmd.index("-ss") + 1], "600.000")
        self.assertEqual(cmd[cmd.index("-live_start_index") + 1], "0")
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertNotIn("-ss", tuner.stream_cmd("http://x/p.m3u8"))

    def test_live_tv_lists_the_channels_and_whats_on(self):
        didl, n, total = self.result(self.browse("live"))
        self.assertEqual((n, total), (2, 2))
        first, second = didl.findall("d:item", NS)
        self.assertEqual(first.findtext("dc:title", namespaces=NS), "6.1 WRTV · Jeopardy!")
        self.assertEqual(first.findtext("upnp:albumArtURI", namespaces=NS), "https://x/abc.png")
        res = first.find("d:res", NS)
        self.assertEqual(res.text, "http://192.168.1.69:5004/dlna/ch/6.1.ts")
        self.assertTrue(res.get("protocolInfo").startswith("http-get:*:video/mpeg:"))
        self.assertEqual(second.findtext("dc:title", namespaces=NS), "13.2 Me & You")

    def test_pages(self):
        didl, n, total = self.result(self.browse("live", start=1, count=5))
        self.assertEqual((n, total), (1, 2))
        self.assertEqual(didl.find("d:item", NS).get("id"), "ch-13.2")

    def test_metadata_of_a_channel(self):
        didl, n, _ = self.result(self.browse("ch-13.2", flag="BrowseMetadata"))
        self.assertEqual((n, didl.find("d:item", NS).get("parentID")), (1, "live"))

    def test_unknown_object(self):
        r = self.browse("ch-99.9", flag="BrowseMetadata")
        self.assertEqual(r.status_code, 500)
        self.assertIn(b"<errorCode>701</errorCode>", r.content)

    def test_asking_about_a_channel_doesnt_tune_it(self):
        with mock.patch.object(tuner, "channel_stream", new=mock.AsyncMock()) as stream:
            r = self.client().head("/dlna/ch/6.1.ts")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["transferMode.dlna.org"], "Streaming")
            self.assertEqual(self.client().head("/dlna/ch/99.9.ts").status_code, 404)
            stream.assert_not_called()

    def test_away_from_home_is_refused(self):
        self.assertEqual(self.client("8.8.8.8").get("/dlna/device.xml").status_code, 403)

    def test_search_replies(self):
        msg = (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\n'
               b"ST: urn:schemas-upnp-org:device:MediaServer:1\r\n\r\n")
        st, mx = dlna.parse_search(msg)
        self.assertEqual((st, mx), (dlna.DEVICE, 2))
        loc = "http://192.168.1.69:5004/dlna/device.xml"
        (reply,) = dlna.search_reply(st, loc)
        self.assertTrue(reply.startswith("HTTP/1.1 200 OK\r\n"))
        self.assertIn(f"LOCATION: {loc}\r\n", reply)
        self.assertIn(f"USN: {dlna.udn()}::{dlna.DEVICE}\r\n", reply)
        self.assertEqual(len(dlna.search_reply("ssdp:all", loc)), 5)
        self.assertEqual(dlna.search_reply("urn:schemas-upnp-org:device:MediaRenderer:1", loc), [])
        self.assertIsNone(dlna.parse_search(b"NOTIFY * HTTP/1.1\r\nNT: x\r\n\r\n"))

    def test_goodbye_has_no_address(self):
        alive = dlna.notify("ssdp:alive", "http://x/dlna/device.xml")
        bye = dlna.notify("ssdp:byebye", "http://x/dlna/device.xml")
        self.assertTrue(all("LOCATION:" in m for m in alive))
        self.assertFalse(any("LOCATION:" in m for m in bye))


if __name__ == "__main__":
    unittest.main()
