try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import gzip
import unittest
from unittest import mock
from datetime import datetime, timezone

from app import extra_channels as xc

M3U = '''#EXTM3U url-tvg="https://example.com/epg.xml.gz"
#EXTINF:-1 tvg-id="news.1" tvg-logo="https://example.com/n.png" tvg-chno="101" group-title="News",News Now
https://example.com/news/master.m3u8
#EXTINF:-1 tvg-id="movies" group-title="Movies, Classic",Old Movies
#EXTVLCOPT:http-user-agent=Something
https://example.com/movies.m3u8
#EXTINF:-1,Not a web address
rtmp://example.com/x
#EXTINF:-1 tvg-id="news.1",News Now again
https://example.com/news/master.m3u8
'''

XMLTV = b'''<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="news.1"><display-name>News Now</display-name></channel>
  <programme start="20261106170000 +0000" stop="20261106180000 +0000" channel="news.1">
    <title>Evening News</title><sub-title>Friday</sub-title><desc>The day's news.</desc>
    <category>News</category><icon src="https://example.com/p.jpg"/>
    <episode-num system="xmltv_ns">2.4.</episode-num><new/>
  </programme>
  <programme start="20261106130000 -0500" stop="20261106140000 -0500" channel="news.1"><title>Later</title></programme>
  <programme start="20261101170000 +0000" stop="20261101180000 +0000" channel="news.1"><title>Last week</title></programme>
  <programme start="20261106170000 +0000" stop="20261106180000 +0000" channel="other"><title>Not ours</title></programme>
</tv>'''


class ExtraChannelTests(unittest.TestCase):
    def test_playlist(self):
        chans = xc.parse_m3u(M3U)
        self.assertEqual([c["name"] for c in chans], ["News Now", "Old Movies"])  # one per address, web only
        news, movies = chans
        self.assertTrue(xc.is_extra(news["id"]))
        self.assertEqual((news["tvg_id"], news["number"], news["group"], news["logo"]),
                         ("news.1", "101", "News", "https://example.com/n.png"))
        self.assertEqual(movies["group"], "Movies, Classic")
        self.assertEqual(movies["url"], "https://example.com/movies.m3u8")
        self.assertFalse(xc.is_extra("S123"))

    def test_guide(self):
        now = datetime(2026, 11, 6, 17, 30, tzinfo=timezone.utc)
        for data in (XMLTV, gzip.compress(XMLTV)):
            by = xc.parse_xmltv(data, {"news.1"}, now)
            self.assertEqual(list(by), ["news.1"])
            first, later = by["news.1"]  # last week's is outside the window
            self.assertEqual(first["title"], "Evening News")
            self.assertEqual((first["season_number"], first["episode_number"]), (3, 5))
            self.assertEqual(first["air_datetime"], "2026-11-06T17:00:00Z")
            self.assertEqual(first["duration"], 3600)
            self.assertTrue(first["is_new"])
            self.assertTrue(first["path"].startswith("/channel/"))  # never offered for recording
            self.assertEqual(later["air_datetime"], "2026-11-06T18:00:00Z")  # -0500 read as UTC

    def test_same_channel_at_a_new_address(self):
        old = xc.parse_m3u(M3U)[0]
        moved = xc.parse_m3u(M3U.replace("https://example.com/news/master.m3u8", "https://example.com/news/v2.m3u8"))
        with mock.patch.dict(xc._playlist, {"channels": moved}):
            found = xc.find_same(old)
        self.assertEqual(found["url"], "https://example.com/news/v2.m3u8")
        self.assertNotEqual(found["id"], old["id"])

    def test_movies_and_series_left_out(self):
        # A provider's list (Xtream): live channels, then its films and every episode of every series
        chans = xc.parse_m3u('''#EXTM3U
#EXTINF:-1 tvg-id="a" group-title="US News",CNN
http://iptv.example:8080/live/u/p/101.ts
#EXTINF:-1 group-title="US",ABC
http://iptv.example:8080/u/p/102
#EXTINF:-1 group-title="Movies",Some Film (2020)
http://iptv.example:8080/movie/u/p/5001.mkv
#EXTINF:-1 group-title="Series",Some Show S01 E01
http://iptv.example:8080/series/u/p/9001.mp4
#EXTINF:-1,A file
https://cdn.example/clip.mp4?token=1
''')
        self.assertEqual([c["name"] for c in chans], ["CNN", "ABC"])


class BigPlaylistTests(unittest.TestCase):
    """A playlist of hundreds of thousands of channels hung the browser: the guide gets the
    favorites only, and the More tab a page at a time, searched on the server."""
    def setUp(self):
        self.chans = [{"id": f"x-{i:010x}", "name": f"Channel {i}", "url": f"https://e/{i}.m3u8", "logo": None,
                       "tvg_id": "", "number": "", "group": "Sports" if i % 2 else "News"} for i in range(xc.IN_GUIDE + 500)]
        self.window = (datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc), datetime(2026, 11, 18, 2, 0, tzinfo=timezone.utc))
        marks = {"favorite": {"name:Channel 7"}, "hidden": {"name:Channel 1", "name:Channel 3"}, "groups": set()}
        self.patches = [mock.patch.object(xc, "channels", mock.AsyncMock(return_value=self.chans)),
                        mock.patch.object(xc, "guide_for", return_value={}),
                        mock.patch.object(xc, "marks", return_value=marks)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_async(self, coro):
        import asyncio
        return asyncio.run(coro)

    def test_the_guide_gets_only_the_favorites(self):
        rows, left_out = self.run_async(xc.epg_rows(*self.window, "2026-11-17T20:00:00Z", 6))
        self.assertEqual([r["name"] for r in rows], ["Channel 7"])
        self.assertEqual(left_out, len(self.chans) - 1)

    def test_a_small_playlist_goes_whole(self):
        del self.chans[100:]
        rows, left_out = self.run_async(xc.epg_rows(*self.window, "2026-11-17T20:00:00Z", 6))
        self.assertEqual((len(rows), left_out), (100, 0))

    def test_pages_without_the_hidden(self):
        res = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6))
        self.assertEqual(len(res["rows"]), xc.PAGE)
        self.assertEqual((res["total"], res["hidden"]), (len(self.chans) - 2, 2))
        self.assertEqual([r["name"] for r in res["rows"][:3]], ["Channel 0", "Channel 2", "Channel 4"])
        nxt = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6, offset=xc.PAGE))
        self.assertNotIn(nxt["rows"][0]["name"], [r["name"] for r in res["rows"]])

    def test_search_every_word_in_the_name_or_group(self):
        res = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6, q="sports channel 35"))
        self.assertEqual([r["name"] for r in res["rows"]][:3], ["Channel 35", "Channel 135", "Channel 235"])
        self.assertTrue(all(int(r["name"].split()[1]) % 2 for r in res["rows"]))

    def test_groups_listed_picked_and_hidden(self):
        res = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6))
        self.assertEqual([(g["name"], g["hidden"]) for g in res["groups"]], [("News", False), ("Sports", False)])
        self.assertNotIn("groups", self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6, offset=xc.PAGE)))
        xc.marks.return_value["groups"] = {"Sports"}
        res = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6))
        self.assertTrue(all(r["group"] == "News" if "group" in r else r["network"] == "News" for r in res["rows"]))
        picked = self.run_async(xc.page(*self.window, "2026-11-17T20:00:00Z", 6, group="Sports"))
        self.assertEqual(picked["total"], (len(self.chans) // 2) - 2)  # a hidden group shows when picked (less 1 and 3)
        self.assertTrue(all(r["group_hidden"] and r["hidden"] for r in picked["rows"]))


if __name__ == "__main__":
    unittest.main()
