try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import unittest

from app import database as db
from app import streaming

IDENT = "C32898436_SHOW_SH063946840000"


def ota(airings):
    return {"channel": {"identifier": "S36147_029_01", "kind": "ota"}, "airings": airings}


def airing(ident, images):
    return {"show": {"identifier": ident, "title": "Eternally Yours"}, "images": images}


IMAGES = [{"kind": "poster", "url": "https://cdn/p_b_v13.jpg"},
          {"kind": "coverLarge", "url": "https://cdn/p_b_h8.jpg?w=1280"},
          {"kind": "background", "url": "https://cdn/p_i_h8.jpg"},
          {"kind": "backdropLarge", "url": "https://cdn/p_bd_h8.jpg?w=1280"}]


class CloudArtTests(unittest.TestCase):
    """Antenna shows' artwork from Tablo's cloud guide: the Tablo's own guide kept a stock picture
    (remotes and pretzels) for a new CBS series the cloud had real artwork for."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for t in ("cloud_art", "guide_shows", "shows"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def guide_show(self, cover="/api/images/206443"):
        db.upsert_guide_show({"path": "/guide/series/206441", "title": "Eternally Yours", "cover_url": cover,
                              "backdrop_url": "/api/images/206444", "raw_json": {"identifier": IDENT}})

    def recorded_show(self):
        db.upsert_show({"id": "rec1", "title": "Eternally Yours", "cover_url": "/api/images/206443",
                        "backdrop_url": "/api/images/206444", "raw_json": {"guide_path": "/guide/series/206441"}})

    def row(self, table, key, value):
        with db.get_connection() as conn:
            return dict(conn.execute(f"SELECT cover_url, backdrop_url FROM {table} WHERE {key} = ?", (value,)).fetchone())

    def test_picks_the_cover_and_backdrop_of_antenna_shows(self):
        grid = [ota([airing(IDENT, IMAGES)]),
                {"channel": {"identifier": "ION", "kind": "ott"}, "airings": [airing("STREAM_SHOW", IMAGES)]}]
        self.assertEqual(streaming.art_from_grid(grid),
                         {IDENT: {"cover_url": "https://cdn/p_b_h8.jpg?w=1280", "backdrop_url": "https://cdn/p_bd_h8.jpg?w=1280"}})
        self.assertEqual(streaming.art_from_grid([ota([airing(IDENT, [])])]), {})

    def test_applied_to_the_guide_and_the_recorded_show(self):
        self.guide_show()
        self.recorded_show()
        self.assertEqual(db.save_cloud_art({IDENT: {"cover_url": "https://cdn/c.jpg", "backdrop_url": "https://cdn/b.jpg"}}), 2)
        want = {"cover_url": "https://cdn/c.jpg", "backdrop_url": "https://cdn/b.jpg"}
        self.assertEqual(self.row("guide_shows", "path", "/guide/series/206441"), want)
        self.assertEqual(self.row("shows", "id", "rec1"), want)

    def test_the_next_tablo_sync_keeps_it(self):
        self.guide_show()
        self.recorded_show()
        db.save_cloud_art({IDENT: {"cover_url": "https://cdn/c.jpg", "backdrop_url": None}})
        self.guide_show()  # the Tablo's guide again, still the stock picture
        self.recorded_show()
        self.assertEqual(self.row("guide_shows", "path", "/guide/series/206441"),
                         {"cover_url": "https://cdn/c.jpg", "backdrop_url": "/api/images/206444"})
        self.assertEqual(self.row("shows", "id", "rec1")["cover_url"], "https://cdn/c.jpg")

    def test_shows_the_cloud_has_nothing_for_keep_the_tablos(self):
        self.guide_show()
        db.save_cloud_art({"OTHER_SHOW": {"cover_url": "https://cdn/o.jpg", "backdrop_url": None}})
        self.assertEqual(self.row("guide_shows", "path", "/guide/series/206441")["cover_url"], "/api/images/206443")

    def test_a_guide_entry_without_details_doesnt_stop_it(self):
        # (some of the Tablo's guide entries are saved with an empty raw_json)
        db.upsert_guide_show({"path": "/guide/series/1", "title": "Bare", "raw_json": ""})
        self.guide_show()
        self.recorded_show()
        self.assertEqual(db.save_cloud_art({IDENT: {"cover_url": "https://cdn/c.jpg", "backdrop_url": None}}), 2)

    def test_loaded_right_after_the_update(self):
        db.set_sync_meta("last_streaming_sync", "2999-01-01T00:00:00+00:00")
        db.set_sync_meta("cloud_art_version", "0")
        self.assertTrue(streaming.due())
        db.set_sync_meta("cloud_art_version", str(streaming.CLOUD_ART_VERSION))
        self.assertFalse(streaming.due())


if __name__ == "__main__":
    unittest.main()
