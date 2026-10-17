import unittest

from app.routes.live import channel_categories, pick_logo


def channel(name, *genre_lists, minutes=30):
    return {"name": name, "airings": [{"duration": minutes * 60, "genres": list(g)} for g in genre_lists]}


class CategoryTests(unittest.TestCase):
    def test_mostly_news_is_news(self):
        self.assertEqual(channel_categories(channel("KXYZ", ["News"], ["News"], ["Sitcom"])), ["news"])

    def test_sports_genres(self):
        self.assertEqual(channel_categories(channel("Stadium", ["Sports event"], ["Football"])), ["sports"])

    def test_sports_category_counts(self):
        c = {"name": "X", "airings": [{"duration": 3600, "genres": [], "category": "sports"}]}
        self.assertEqual(channel_categories(c), ["sports"])

    def test_everything_else_is_entertainment(self):
        self.assertEqual(channel_categories(channel("Classic TV", ["Drama"], ["Comedy"])), ["entertainment"])

    def test_talk_shows_are_not_news(self):
        self.assertEqual(channel_categories(channel("Nosey", ["Talk"], ["Talk"])), ["entertainment"])

    def test_channel_name_hint(self):
        self.assertIn("news", channel_categories(channel("Scripps News", ["Documentary"])))
        self.assertIn("sports", channel_categories(channel("NASCAR Sports", ["Documentary"])))

    def test_no_airings(self):
        self.assertEqual(channel_categories({"name": "Empty", "airings": []}), ["entertainment"])


class LogoTests(unittest.TestCase):
    def test_prefers_white_logo_for_dark_ui(self):
        logos = [{"kind": "darkLarge", "url": "black.png"}, {"kind": "lightLarge", "url": "white.png"},
                 {"kind": "originalLarge", "url": "color.png"}]
        self.assertEqual(pick_logo(logos), "white.png")

    def test_falls_back(self):
        self.assertEqual(pick_logo([{"kind": "darkLarge", "url": "black.png"}]), "black.png")
        self.assertIsNone(pick_logo([]))


if __name__ == "__main__":
    unittest.main()
