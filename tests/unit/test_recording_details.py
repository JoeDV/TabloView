import unittest

from app.database import recording_details


def airing(state="finished", end=60, protected=False, snapshot=317522, seek=15, error=None):
    """A recording object shaped like the Tablo's /recordings/series/episodes/<id> response."""
    return {
        "snapshot_image": {"image_id": snapshot, "has_title": True} if snapshot else None,
        "video_details": {"state": state, "duration": 1875, "seek": seek, "error": error,
                          "recorded_offsets": {"start": -15, "end": end}},
        "user_info": {"position": 0, "watched": False, "protected": protected},
    }


class RecordingDetailsTests(unittest.TestCase):
    def test_complete_recording(self):
        d = recording_details(airing())
        self.assertFalse(d["incomplete"])
        self.assertEqual(d["ended_early"], 0)
        self.assertEqual(d["snapshot_url"], "/api/images/317522")
        self.assertEqual(d["program_start"], 15)
        self.assertFalse(d["protected"])

    def test_recording_that_stopped_early_is_short(self):
        d = recording_details(airing(end=-509))
        self.assertTrue(d["incomplete"])
        self.assertEqual(d["ended_early"], 509)

    def test_a_few_seconds_early_is_not_short(self):
        self.assertFalse(recording_details(airing(end=-30))["incomplete"])

    def test_failed_recording_is_incomplete_but_not_short(self):
        d = recording_details(airing(state="failed", end=-2686, error={"details": "weak_signal"}))
        self.assertTrue(d["incomplete"])
        self.assertEqual(d["ended_early"], 0)  # shown as Failed/Partial instead

    def test_protected_and_missing_snapshot(self):
        d = recording_details(airing(protected=True, snapshot=None))
        self.assertTrue(d["protected"])
        self.assertIsNone(d["snapshot_url"])

    def test_accepts_json_text_and_bad_input(self):
        self.assertEqual(recording_details('{"video_details": {"seek": 15}}')["program_start"], 15)
        self.assertFalse(recording_details("not json")["incomplete"])
        self.assertFalse(recording_details(None)["protected"])


if __name__ == "__main__":
    unittest.main()
