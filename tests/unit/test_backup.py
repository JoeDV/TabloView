try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import json
import unittest
from datetime import datetime, timedelta, timezone

from app import backup, reminders
from app import database as db
from app.settings import load_settings, save_settings


def ep(ep_id):
    return {"id": ep_id, "show_id": "bk-show", "show_title": "Backup Show", "path": f"/recordings/series/episodes/{ep_id}",
            "title": ep_id, "raw_json": {}}


class BackupTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            for table in ("shows", "episodes", "watch_list", "commercials", "auto_exports", "recording_history", "dropouts"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        reminders._save([])
        db.upsert_show({"id": "bk-show", "title": "Backup Show"})
        for i in ("e1", "e2", "e3"):
            db.upsert_episode(ep(i))
        self.saved = load_settings()
        self.addCleanup(lambda: save_settings(self.saved))

    def old_pc(self):
        save_settings({"skip_commercials": True, "commercial_shows": ["bk-show"], "claude_api_key": "sk-secret",
                       "plex_token": "plex-secret", "lan_pin": {"salt": "s", "hash": "h"}, "export_folder": r"Z:\nowhere\at all"})
        db.set_watch_list(["e2", "e1"])
        db.save_commercials("e1", "done", [{"start": 60, "end": 180}], by_claude=True)
        db.save_auto_export("e1", "bk-show", "done")
        db.save_auto_export("e2", "bk-show", "queued", "job-1", tries=1)
        start = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        reminders.add({"channel_key": "c1", "channel_id": "1", "channel_name": "WTHR", "title": "News", "start": start, "duration": 1800})
        return backup.make({"tablo_volume": 0.4, "tv_view": "1", "other": "x"})

    def new_pc(self):
        """This PC wiped, as a new PC would be after its first sync."""
        save_settings({"skip_commercials": False, "commercial_shows": [], "claude_api_key": "sk-mine", "plex_token": None,
                       "lan_pin": None, "export_folder": None})
        with db.get_connection() as conn:
            for table in ("watch_list", "commercials", "auto_exports"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        reminders._save([])

    def test_secrets_are_left_out(self):
        text = backup.dumps(self.old_pc())
        for secret in ("sk-secret", "plex-secret", "lan_pin", "claude_api_key"):
            self.assertNotIn(secret, text)
        data = json.loads(text)
        self.assertEqual(data["browser"], {"tablo_volume": "0.4"})  # not which view, not unknown keys
        self.assertEqual(data["watch_list"], ["e2", "e1"])

    def test_restore_on_a_new_pc(self):
        data = json.loads(backup.dumps(self.old_pc()))
        self.new_pc()
        out = backup.restore(data)
        s = load_settings()
        self.assertTrue(s["skip_commercials"])
        self.assertEqual(s["commercial_shows"], ["bk-show"])
        self.assertEqual(s["claude_api_key"], "sk-mine")  # this PC's key kept
        self.assertIsNone(s["export_folder"])  # that folder isn't here
        self.assertTrue(any("export folder" in n for n in out["notes"]))
        self.assertEqual([r["id"] for r in db.get_watch_list()], ["e2", "e1"])
        self.assertEqual(db.get_commercials(["e1"])["e1"]["status"], "done")
        exports = db.get_auto_exports(["bk-show"])
        self.assertEqual(exports["e1"]["state"], "done")
        self.assertEqual((exports["e2"]["state"], exports["e2"]["job_id"]), ("pending", None))  # its export was on the old PC
        self.assertEqual(len(reminders.listing()), 1)
        self.assertEqual(out["browser"], {"tablo_volume": "0.4"})
        self.assertEqual((out["watch_list"], out["commercials"], out["reminders"]), (2, 1, 1))

    def test_restoring_twice_adds_nothing(self):
        data = json.loads(backup.dumps(self.old_pc()))
        out = backup.restore(data)
        self.assertEqual((out["watch_list"], out["commercials"], out["reminders"]), (0, 0, 0))
        self.assertEqual(len(db.get_watch_list()), 2)

    def test_what_is_here_wins(self):
        data = json.loads(backup.dumps(self.old_pc()))
        db.save_commercials("e1", "done", [{"start": 10, "end": 20}])
        backup.restore(data)
        self.assertEqual(db.get_commercials(["e1"])["e1"]["breaks"][0]["start"], 10)

    def test_gone_recordings_and_bad_files(self):
        data = json.loads(backup.dumps(self.old_pc()))
        data["watch_list"].append("not-here")
        self.new_pc()
        self.assertTrue(any("1 recording" in n for n in backup.restore(data)["notes"]))
        with self.assertRaises(backup.BackupError):
            backup.restore({"settings": {}})
        with self.assertRaises(backup.BackupError):
            backup.restore({**data, "format": 99})

    def test_needs_the_first_sync(self):
        data = backup.make({})
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.commit()
        with self.assertRaisesRegex(backup.BackupError, "Sign in"):
            backup.restore(data)


if __name__ == "__main__":
    unittest.main()
