import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

from app import commercials
from app import database as db
from app.routes import shows
from app.sync_service import slugify_show_title


class SeriesCommercialsTests(unittest.TestCase):
    """Skip commercials turned on from a series' guide page, before anything has recorded: saved under
    the id its recordings will get when they sync."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM shows")
            conn.commit()
        self.settings = {"commercial_shows": []}
        for p in (mock.patch.object(commercials, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(commercials, "save_settings", side_effect=lambda u: self.settings.update(u))):
            p.start()
            self.addCleanup(p.stop)

    def test_by_title_before_any_recording(self):
        res = asyncio.run(shows.set_commercials(shows.CommercialsRequest(on=True), title="Murdoch Mysteries"))
        self.assertIsNone(res["show"])
        self.assertEqual(self.settings["commercial_shows"], [slugify_show_title("Murdoch Mysteries")])
        self.assertTrue(asyncio.run(shows.get_commercials_setting(title="Murdoch Mysteries"))["on"])
        asyncio.run(shows.set_commercials(shows.CommercialsRequest(on=False), title="Murdoch Mysteries"))
        self.assertFalse(asyncio.run(shows.get_commercials_setting(title="Murdoch Mysteries"))["on"])

    def test_unknown_show_id_still_refused(self):
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(shows.set_commercials(shows.CommercialsRequest(on=True), show_id="nope"))
        self.assertEqual(cm.exception.status_code, 404)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(shows.get_commercials_setting())
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
