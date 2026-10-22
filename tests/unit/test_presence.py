import unittest

from app import presence


class PresenceTests(unittest.TestCase):
    """The tray's one-time "still running" notice: when the last TabloView page has been closed."""

    def setUp(self):
        presence._last_seen = 0.0
        self.addCleanup(setattr, presence, "_last_seen", 0.0)

    def test_no_page_yet_is_not_closed(self):
        # Started at sign-in, in the tray: no page has been opened, so nothing to say
        self.assertFalse(presence.pages_closed(now=10_000))

    def test_closed_after_a_long_silence(self):
        presence.page_seen(now=1_000)
        self.assertFalse(presence.pages_closed(now=1_000 + 60))  # a tab in the background, slowed down
        self.assertTrue(presence.pages_closed(now=1_000 + presence.PAGE_GONE_SECONDS + 1))


if __name__ == "__main__":
    unittest.main()
