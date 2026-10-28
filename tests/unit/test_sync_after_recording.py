import unittest
from datetime import datetime, timedelta, timezone

from app import database as db
from app import sync_service


def episode(id, start, state, duration=3600):
    return {"id": id, "show_id": "ncis-origins", "show_title": "NCIS: Origins", "path": f"/recordings/series/episodes/{id}",
            "season_number": 3, "episode_number": 4, "title": "t", "air_date": start.strftime("%Y-%m-%dT%H:%MZ"),
            "duration": duration, "status": "Unwatched", "raw_json": {"video_details": {"state": state}}}


class SyncAfterRecordingTests(unittest.TestCase):
    """A recording that has reached its scheduled end gets a sync soon after, so it stops saying
    Recording without waiting for the next scheduled sync (forum: NCIS: Origins, 2026-10-27)."""

    def setUp(self):
        db.init_db()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM episodes")
            conn.commit()
        self.now = datetime.now(timezone.utc)

    def test_ended_after_last_sync(self):
        db.upsert_episode(episode("a", self.now - timedelta(minutes=65), "recording"))
        # last synced 10 minutes ago, before its end (5 minutes ago) plus the grace
        self.assertTrue(sync_service._ended_since_sync(600))
        # synced 2 minutes ago, after its end: the Tablo still records it (a game running long)
        self.assertFalse(sync_service._ended_since_sync(120))

    def test_still_on_or_finished(self):
        db.upsert_episode(episode("b", self.now - timedelta(minutes=30), "recording"))
        db.upsert_episode(episode("c", self.now - timedelta(minutes=90), "finished"))
        self.assertFalse(sync_service._ended_since_sync(3600))


if __name__ == "__main__":
    unittest.main()
