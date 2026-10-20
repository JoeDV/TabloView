import unittest

from app.routes.guide import airings_list_path
from app.sync_service import guide_airing_row

# A sports event as the Tablo returns it (WTHR, 2026-10-20), trimmed
EVENT = {
    "path": "/guide/sports/events/298974",
    "object_id": 298974,
    "sport_path": "/guide/sports/298970",
    "event": {"title": "Philadelphia 76ers at New York Knicks", "venue": "Madison Square Garden",
              "teams": [{"name": "Philadelphia 76ers"}, {"name": "New York Knicks"}]},
    "qualifiers": ["live", "cc", "primetime"],
    "schedule": {"state": "none"},
    "airing_details": {"datetime": "2026-10-20T23:00Z", "duration": 9000, "show_title": "NBA Basketball",
                       "channel": {"channel": {"call_sign": "WTHR", "network": "NBC",
                                               "channel_identifier": "S19593_013_01"}}},
}


class SportsGuideTests(unittest.TestCase):
    """Sports events belong to their league, and are named by the game."""

    def test_an_event_is_linked_to_its_league(self):
        row = guide_airing_row(EVENT["path"], EVENT)
        self.assertEqual(row["series_path"], "/guide/sports/298970")

    def test_an_event_is_named_by_the_game(self):
        row = guide_airing_row(EVENT["path"], EVENT)
        self.assertEqual(row["episode_title"], "Philadelphia 76ers at New York Knicks")
        self.assertEqual(row["show_title"], "NBA Basketball")

    def test_series_episodes_are_unchanged(self):
        ep = {"series_path": "/guide/series/1", "episode": {"title": "Pilot", "number": 1, "season_number": 1},
              "airing_details": {"show_title": "A Show", "channel": {"channel": {}}}}
        row = guide_airing_row("/guide/series/episodes/2", ep)
        self.assertEqual((row["series_path"], row["episode_title"]), ("/guide/series/1", "Pilot"))

    def test_a_league_lists_its_games_as_events(self):
        # /guide/sports/<id>/episodes is "not found" on the Tablo
        self.assertEqual(airings_list_path("/guide/sports/298970"), "/guide/sports/298970/events")
        self.assertEqual(airings_list_path("/guide/series/25778"), "/guide/series/25778/episodes")


if __name__ == "__main__":
    unittest.main()
