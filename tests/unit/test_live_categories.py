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
    LOGOS = [{"kind": "darkLarge", "url": "black.png"}, {"kind": "lightLarge", "url": "white.png"},
             {"kind": "originalLarge", "url": "color.png"}]

    def test_color_by_default(self):
        # "originalLarge" is the station's own colors (NBC's peacock)
        self.assertEqual(pick_logo(self.LOGOS, "color"), "color.png")

    def test_white_when_chosen(self):
        self.assertEqual(pick_logo(self.LOGOS, "white"), "white.png")

    def test_falls_back(self):
        self.assertEqual(pick_logo([{"kind": "darkLarge", "url": "black.png"}], "color"), "black.png")
        self.assertEqual(pick_logo([{"kind": "originalLarge", "url": "color.png"}], "white"), "color.png")
        self.assertIsNone(pick_logo([], "color"))

    def test_the_setting_decides_when_no_style_is_given(self):
        from unittest import mock
        from app.routes import live
        with mock.patch.object(live, "logo_style", return_value="white"):
            self.assertEqual(pick_logo(self.LOGOS), "white.png")


if __name__ == "__main__":
    unittest.main()
