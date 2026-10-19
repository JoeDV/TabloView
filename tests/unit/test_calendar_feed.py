import unittest
from datetime import datetime, timezone

from app import calendar_feed

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def airing(**kw):
    a = {"path": "/guide/series/episodes/298933", "show_title": "Jeopardy!", "episode_title": "Episode 26",
         "season_number": 43, "episode_number": 26, "air_datetime": "2026-10-19T23:30Z", "duration": 1800,
         "channel_network": "NBC", "channel_call_sign": "WTHR", "is_new": True}
    a.update(kw)
    return a


class CalendarFeedTests(unittest.TestCase):
    def test_an_event_per_recording_with_a_stable_id(self):
        ics = calendar_feed.build([airing()], now=NOW)
        self.assertIn("UID:guide-series-episodes-298933@tabloview\r\n", ics)
        self.assertIn("DTSTART:20261019T233000Z\r\n", ics)
        self.assertIn("DTEND:20261020T000000Z\r\n", ics)
        self.assertIn("SUMMARY:Jeopardy! — S43E26 · Episode 26\r\n", ics)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n"))

    def test_text_is_escaped_and_long_lines_folded(self):
        ics = calendar_feed.build([airing(episode_title="Housewives, Hoops & Hits; " + "x" * 120)], now=NOW)
        self.assertIn("Housewives\\, Hoops & Hits\\;", ics)
        self.assertTrue(all(len(line.encode()) <= 75 for line in ics.split("\r\n")))
        unfolded = ics.replace("\r\n ", "")
        self.assertIn("x" * 120, unfolded)

    def test_bad_times_are_skipped(self):
        self.assertNotIn("BEGIN:VEVENT", calendar_feed.build([airing(air_datetime="soon")], now=NOW))


if __name__ == "__main__":
    unittest.main()
