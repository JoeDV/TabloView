import asyncio
import unittest
from unittest import mock

from app import autoexport
from app import database as db
from app.tablo_client import tablo_manager
from app.transcode import transcode_manager


def episode(id, show, state="finished", air="2026-10-10T00:00Z"):
    return {"id": id, "show_id": show, "show_title": show, "path": f"/recordings/series/episodes/{id}", "season_number": 1,
            "episode_number": 1, "title": id, "air_date": air, "duration": 1800, "status": "Unwatched",
            "raw_json": {"video_details": {"state": state}}}


class AutoExportTests(unittest.TestCase):
    """A show set to export automatically: each finished recording exported once, one at a time,
    tried again when an export fails, never again when one was cancelled."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("episodes", "auto_exports", "exports"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        for ep in (episode("a1", "showa"), episode("a2", "showa"), episode("a3", "showa", state="recording"),
                   episode("b1", "showb")):
            db.upsert_episode(ep)
        self.settings = {"auto_export_shows": []}
        self.started = []

        async def start(ep, get_url):
            job = f"job{len(self.started) + 1}"
            self.started.append(ep["id"])
            db.save_export_job({"job_id": job, "episode_id": ep["id"], "title": "t", "filename": "f.mp4", "filepath": "f.mp4",
                                "status": "pending", "progress": 0.0, "file_size": 0, "error": None, "created_at": "2026-10-27"})
            return job
        for p in (mock.patch.object(autoexport, "load_settings", side_effect=lambda: dict(self.settings)),
                  mock.patch.object(autoexport, "save_settings", side_effect=lambda u: self.settings.update(u)),
                  mock.patch.object(autoexport, "_low_space", return_value=False),
                  mock.patch.object(transcode_manager, "start_mp4_export", side_effect=start),
                  mock.patch.object(tablo_manager, "playlist_getter", return_value=None)):
            p.start()
            self.addCleanup(p.stop)

    def run_once(self):
        asyncio.run(autoexport.run_once())

    def finish(self, job, result="completed"):
        db.save_export_job({"job_id": job, "status": result, "progress": 1.0})

    def test_new_ones_only_skips_what_was_recorded_already(self):
        self.assertEqual(autoexport.already_recorded("showa"), 2)
        self.assertEqual(autoexport.set_show("showa", True), 0)
        self.run_once()
        self.assertEqual(self.started, [])
        # The one recording now finishes: it's new, so it's exported
        db.upsert_episode(episode("a3", "showa"))
        self.run_once()
        self.assertEqual(self.started, ["a3"])

    def test_those_too_exports_them_one_at_a_time_and_each_once(self):
        self.assertEqual(autoexport.set_show("showa", True, existing=True), 2)
        self.run_once()
        self.run_once()  # the first is still waiting: nothing more queued
        self.assertEqual(len(self.started), 1)
        self.finish("job1")
        self.run_once()
        self.finish("job2")
        self.run_once()
        self.run_once()
        self.assertEqual(sorted(self.started), ["a1", "a2"])
        self.assertEqual(autoexport.waiting("showa"), 0)
        self.assertEqual(autoexport.already_recorded("showa"), 0)
        # Other shows aren't touched
        self.assertNotIn("b1", self.started)

    def test_failed_exports_are_tried_again_then_given_up_and_cancelled_ones_left(self):
        autoexport.set_show("showb", True, existing=True)
        for n in range(autoexport.TRIES):
            self.run_once()
            self.finish(f"job{n + 1}", "failed")
        self.run_once()
        self.assertEqual(self.started, ["b1"] * autoexport.TRIES)
        self.assertEqual(db.get_auto_exports()["b1"]["state"], "gave_up")
        db.upsert_episode(episode("b2", "showb"))
        self.run_once()
        self.finish(f"job{autoexport.TRIES + 1}", "cancelled")
        self.run_once()
        self.run_once()
        self.assertEqual(db.get_auto_exports()["b2"]["state"], "cancelled")
        self.assertEqual(self.started.count("b2"), 1)

    def test_turning_it_off_stops_new_ones(self):
        autoexport.set_show("showa", True)
        autoexport.set_show("showa", False)
        db.upsert_episode(episode("a3", "showa"))
        self.run_once()
        self.assertEqual(self.started, [])
        self.assertEqual(self.settings["auto_export_shows"], [])

    def test_nothing_is_queued_when_the_drive_is_nearly_full(self):
        autoexport.set_show("showa", True, existing=True)
        with mock.patch.object(autoexport, "_low_space", return_value=True):
            self.run_once()
        self.assertEqual(self.started, [])


if __name__ == "__main__":
    unittest.main()
