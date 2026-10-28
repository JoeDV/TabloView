import unittest

from app import plex

LIBS = [
    {"key": "1", "title": "Movies", "type": "movie", "locations": ["/volume1/Plex Videos/Movies"]},
    {"key": "2", "title": "TV Shows", "type": "show", "locations": ["/volume1/Plex Videos/Plex TV"]},
    {"key": "3", "title": "Home videos", "type": "movie", "locations": ["D:\\Home\\TV"]},
]


class PlexMatchTests(unittest.TestCase):
    """An export written through the network is matched to the Plex library holding it, and given to
    Plex in its own terms (forum, 2026-10-28: a Plex folder on a NAS)."""

    def test_network_share_to_nas_path(self):
        lib, path = plex.match(LIBS, r"\\DelveccNAS\Plex Videos\Plex TV\The Price Is Right\Season 55")
        self.assertEqual(lib["key"], "2")
        self.assertEqual(path, "/volume1/Plex Videos/Plex TV/The Price Is Right/Season 55")

    def test_export_folder_itself(self):
        lib, path = plex.match(LIBS, r"\\DelveccNAS\Plex Videos\Plex TV")
        self.assertEqual((lib["key"], path), ("2", "/volume1/Plex Videos/Plex TV"))

    def test_case_and_windows_server(self):
        libs = [{"key": "5", "title": "TV", "type": "show", "locations": ["E:\\Media\\Recorded TV"]}]
        lib, path = plex.match(libs, r"\\server\media\recorded tv\Show")
        self.assertEqual(path, "E:\\Media\\Recorded TV\\Show")

    def test_not_in_a_library(self):
        self.assertIsNone(plex.match(LIBS, r"C:\Users\Joe\Downloads\TabloView\Show"))
        # the share above the library's folder isn't inside it
        self.assertIsNone(plex.match(LIBS, r"\\DelveccNAS\Plex Videos\Show"))

    def test_longest_match_wins(self):
        # "TV" alone matches the Home videos library, but Plex Videos\Plex TV matches more
        libs = LIBS + [{"key": "4", "title": "Other", "type": "show", "locations": ["/mnt/Plex TV"]}]
        lib, _ = plex.match(libs, r"\\DelveccNAS\Plex Videos\Plex TV\Show")
        self.assertEqual(lib["key"], "2")


if __name__ == "__main__":
    unittest.main()
