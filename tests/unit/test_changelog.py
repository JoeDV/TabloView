import unittest
from unittest import mock

from app import whatsnew


class ChangelogTests(unittest.TestCase):
    def test_newest_first_and_nothing_newer_than_the_running_version(self):
        with mock.patch.object(whatsnew, "APP_VERSION", "1.1.4"):
            versions = [v["version"] for v in whatsnew.changelog()]
        self.assertEqual(versions[0], "1.1.4")
        self.assertNotIn("1.1.5", versions)
        self.assertEqual(versions[-1], "1.0.0")

    def test_every_version_has_notes(self):
        self.assertTrue(all(notes for notes in whatsnew.NOTES.values()))


if __name__ == "__main__":
    unittest.main()
