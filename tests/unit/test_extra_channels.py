try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import gzip
import unittest
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


if __name__ == "__main__":
    unittest.main()
