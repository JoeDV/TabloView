import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import database as db
from app.transcode import transcode_manager


class ExportNameTests(unittest.TestCase):
    """A forum report: every export of a show the guide doesn't number (Bugs Bunny and Friends on MeTV
    Toons, Friends as filler on a CW station) was "Bugs Bunny and Friends.mp4", each replacing the last."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM exports")
            conn.commit()

    def test_numbered_episodes_keep_their_numbers(self):
        name, label = transcode_manager.export_name({"show_title": "NCIS", "season_number": 24, "episode_number": 4,
                                                     "title": "Like and Subscribe", "air_date": "2026-10-27T00:00Z"})
        self.assertEqual((name, label), ("NCIS - S24E04 - Like and Subscribe.mp4", "NCIS (S24E04)"))

    def test_unnumbered_ones_get_the_local_date_they_aired(self):
        day = datetime.fromisoformat("2026-10-27T15:00+00:00").astimezone().strftime("%Y-%m-%d")
        for title in ("Bugs Bunny and Friends", "", None):
            name, label = transcode_manager.export_name({"show_title": "Bugs Bunny and Friends", "season_number": 0,
                                                         "episode_number": 0, "title": title, "air_date": "2026-10-27T15:00Z"})
            self.assertEqual((name, label), (f"Bugs Bunny and Friends - {day}.mp4", f"Bugs Bunny and Friends ({day})"))

    def test_names_already_used_or_waiting_get_a_number(self):
        folder = Path(tempfile.mkdtemp())
        first = transcode_manager.free_export_path(folder, "Show - 2026-10-27.mp4")
        self.assertEqual(first.name, "Show - 2026-10-27.mp4")
        # Queued, not written yet: the next one queued the same day mustn't get its name
        db.save_export_job({"job_id": "j1", "filename": first.name, "filepath": str(first), "status": "pending"})
        second = transcode_manager.free_export_path(folder, "Show - 2026-10-27.mp4")
        self.assertEqual(second.name, "Show - 2026-10-27 (2).mp4")
        (folder / second.name).write_bytes(b"x")  # on disk already
        db.save_export_job({"job_id": "j1", "status": "completed"})
        self.assertEqual(transcode_manager.free_export_path(folder, "Show - 2026-10-27.mp4").name, "Show - 2026-10-27.mp4")
        self.assertEqual(transcode_manager.free_export_path(folder, "Show - 2026-10-27 (2).mp4").name, "Show - 2026-10-27 (2) (2).mp4")

    def test_a_later_name_change_is_saved_with_the_job(self):
        db.save_export_job({"job_id": "j2", "filename": "a.mp4", "filepath": "C:/x/a.mp4", "status": "pending"})
        db.save_export_job({"job_id": "j2", "status": "downloading"})
        self.assertEqual(db.get_export_job("j2")["filename"], "a.mp4")  # untouched by updates without a name
        db.save_export_job({"job_id": "j2", "status": "downloading", "filename": "a (2).mp4", "filepath": "C:/x/a (2).mp4"})
        self.assertEqual(db.get_export_job("j2")["filepath"], "C:/x/a (2).mp4")


class SortTitleTests(unittest.TestCase):
    def test_a_an_and_the_are_ignored(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE s (title TEXT)")
        titles = ["Terminator 2", "The Addams Family", "A Time to Kill", "Airplane!", "American Experience",
                  "An Officer and a Gentleman", "Theodore Rex", "Anne of Green Gables"]
        conn.executemany("INSERT INTO s VALUES (?)", [(t,) for t in titles])
        got = [r[0] for r in conn.execute(f"SELECT title FROM s ORDER BY {db.sort_title('title')}")]
        self.assertEqual(got, ["The Addams Family", "Airplane!", "American Experience", "Anne of Green Gables",
                               "An Officer and a Gentleman", "Terminator 2", "Theodore Rex", "A Time to Kill"])


if __name__ == "__main__":
    unittest.main()
