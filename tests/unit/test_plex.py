import unittest
from unittest import mock

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



def plex_ep(show="Law & Order", season=3, ep=4, aired="1990-09-13", file="/tv/Law & Order/Season 03/x.mp4", size=100):
    return {"grandparentTitle": show, "parentIndex": season, "index": ep, "originallyAvailableAt": aired,
            "ratingKey": "9", "Media": [{"Part": [{"file": file, "size": size}]}]}


def our_ep(**over):
    ep = {"id": "e1", "show_id": "s1", "path": "/recordings/x", "show_title": "Law & Order", "title": "Pilot",
          "season_number": 3, "episode_number": 4, "air_date": "2026-10-27T01:00Z", "raw_json": "{}",
          "recording_state": "finished", "incomplete": False, "protected": False}
    ep.update(over)
    return ep


class PlexEpisodeTests(unittest.IsolatedAsyncioTestCase):
    """After an export: Plex's own titles for a show, recordings Plex has already, and deleting a
    recording from the Tablo only when Plex has the whole export (forum, 2026-10-28)."""

    def test_same_show(self):
        self.assertTrue(plex.same_show("Law & Order", "Law and Order (1990)"))
        self.assertTrue(plex.same_show("The Price Is Right", "Price Is Right"))
        self.assertTrue(plex.same_show("Mr. Robot", "Mr Robot"))
        self.assertFalse(plex.same_show("Murdoch Mysteries", "The Murders"))
        self.assertFalse(plex.same_show("", "Anything"))

    def test_have(self):
        theirs = [plex_ep(), plex_ep(season=0, ep=0, aired="2026-10-20")]
        ours = [our_ep(), our_ep(id="e2", episode_number=5),
                our_ep(id="e3", season_number=0, episode_number=0, raw_json='{"episode": {"orig_air_date": "2026-10-20"}}'),
                our_ep(id="e4", season_number=0, episode_number=0, raw_json='{"episode": {"orig_air_date": "2026-10-21"}}')]
        self.assertEqual(plex.have(ours, theirs), ["e1", "e3"])

    def test_have_by_file_name(self):
        theirs = [plex_ep(season=9, ep=9, file="/tv/Law & Order/Season 03/Law & Order - S03E05 - Pilot.mp4")]
        self.assertEqual(plex.have([our_ep(episode_number=5)], theirs), ["e1"])

    async def archive(self, ep, shows=("s1",), size=100, deleted=True):
        tablo = mock.Mock(is_authenticated=True, delete_airing=mock.AsyncMock(return_value=deleted))
        with mock.patch.object(plex, "get_episode_by_id", return_value=ep),                 mock.patch.object(plex, "archived_shows", return_value=list(shows)),                 mock.patch.object(plex, "delete_episode") as gone,                 mock.patch("app.tablo_client.tablo_manager", tablo):
            msg = await plex.archive("e1", plex_ep(), "/tv/law & order/Season 03/X.mp4", size)
        return msg, gone.called, tablo.delete_airing.called

    async def test_archive_deletes_when_plex_has_it(self):
        self.assertEqual(await self.archive(our_ep()), ("deleted it from the Tablo", True, True))

    async def test_archive_keeps(self):
        self.assertEqual(await self.archive(our_ep(), shows=()), (None, False, False))
        for ep, size in ((our_ep(protected=True), 100), (our_ep(incomplete=True), 100),
                         (our_ep(recording_state="recording"), 100), (our_ep(), 99)):
            msg, gone, asked = await self.archive(ep, size=size)
            self.assertTrue(msg.startswith("kept it on the Tablo"), msg)
            self.assertFalse(gone or asked)
        msg, gone, _ = await self.archive(our_ep(), deleted=False)
        self.assertFalse(gone)


if __name__ == "__main__":
    unittest.main()
