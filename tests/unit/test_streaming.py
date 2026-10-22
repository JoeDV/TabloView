try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import json
import re
import unittest
from collections import Counter
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app import database as db
from app import streaming
from app.main import app
from app.tablo_client import tablo_manager


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%MZ")


NOW = datetime.now(timezone.utc)


def airing(show, title, kind="episode", genres=(), start=0, minutes=30):
    # Shaped like the cloud's IDs (LH-<episode>-<channel>-T<time>)
    ident = "LH-" + re.sub(r"[^A-Za-z0-9]", "", show + title) + f"-S1_503_01-T{1792600000 + start * 60}"
    return {"identifier": ident, "title": title, "kind": kind, "genres": list(genres),
            "datetime": iso(NOW + timedelta(minutes=start)), "duration": minutes * 60, "description": "d",
            "show": {"identifier": show, "title": show}, "episode": {"season": {"kind": "number", "number": 2}, "episodeNumber": 5},
            "images": [{"kind": "coverLarge", "url": f"https://cdn/{show}.jpg"}], "qualifierTags": ["hdtv"]}


def channel(ident, name, can_record, airings, kind="ott"):
    return {"channel": {"identifier": ident, "name": name, "kind": kind, "logos": [{"kind": "originalLarge", "url": "https://cdn/l.png"}],
                        "ott": {"canRecord": can_record, "channelPartner": "p"}}, "airings": airings}


GRID = [
    channel("ION", "ION", True, [airing("Law & Order", "Ep A", genres=["Crime drama"], start=-10),
                                 airing("Law & Order", "Ep B", genres=["Crime drama"], start=50)]),
    channel("WBD", "Sweet Escapes", False, [airing("Tiny House Hunters", "Tiny", genres=["Reality"], start=30),
                                            airing("Gone", "Old", genres=["Reality"], start=-120, minutes=30)]),
    channel("MOV", "Movies Plus", True, [airing("An Eye for an Eye", "An Eye for an Eye", kind="movieAiring", genres=["Western"], start=90)]),
    channel("ANT", "WTHR", True, [airing("Antenna Show", "x", start=0)], kind="ota"),
]


class StreamingGuideTests(unittest.TestCase):
    """The Guide's Streaming tab: a week of streaming channel listings from Tablo's cloud, by category."""

    def setUp(self):
        db.init_db()
        streaming._shows_cache.update(key=None, shows=[])
        streaming.save(streaming.rows_from_grid(GRID))
        db.set_sync_meta("last_streaming_sync", NOW.isoformat())

    def test_categories(self):
        self.assertEqual(streaming.category(Counter({"movieAiring": 1}), Counter({"western": 1})), "movies")
        self.assertEqual(streaming.category(Counter({"sportEvent": 1}), Counter()), "sports")
        self.assertEqual(streaming.category(Counter({"episode": 3}), Counter({"classic sport event": 1})), "sports")
        self.assertEqual(streaming.category(Counter({"episode": 3}), Counter({"news": 2, "talk": 1})), "news")
        self.assertEqual(streaming.category(Counter({"episode": 3}), Counter({"crime drama": 3})), "drama")
        self.assertEqual(streaming.category(Counter({"episode": 3}), Counter({"talk": 1})), "entertainment")
        self.assertEqual(streaming.category(Counter({"sportEvent": 1}), Counter({"boxing": 1})), "sports")
        self.assertEqual(streaming.category(Counter({"episode": 3}), Counter({"zither": 1})), "other")
        # No genres: the channel decides. A genre-less "movie" too (the cloud calls clip shows films)
        self.assertIsNone(streaming.category(Counter({"episode": 3}), Counter()))
        self.assertIsNone(streaming.category(Counter({"movieAiring": 1}), Counter()))
        self.assertEqual(streaming.channel_hint("BuzzFeed Food"), "reality")
        self.assertEqual(streaming.channel_hint("Women's Sports Network"), "sports")

    def test_only_streaming_channels_and_shows_still_to_come(self):
        titles = [s["title"] for s in streaming.shows()]
        self.assertNotIn("Antenna Show", titles)  # antenna channels are in the Tablo's own guide
        self.assertNotIn("Gone", titles)  # already over
        self.assertEqual(titles[0], "Law & Order")  # on now comes first
        self.assertEqual(set(titles), {"Law & Order", "Tiny House Hunters", "An Eye for an Eye"})

    def test_show_details(self):
        shows = {s["title"]: s for s in streaming.shows()}
        law = shows["Law & Order"]
        self.assertTrue(law["on_now"] and law["can_record"])
        self.assertEqual((law["airings"], law["category"]), (2, "drama"))
        self.assertEqual(law["image"], "https://cdn/Law & Order.jpg")
        self.assertFalse(shows["Tiny House Hunters"]["can_record"])
        self.assertEqual(shows["An Eye for an Eye"]["category"], "movies")

    def test_airings_of_one_show(self):
        airings = streaming.airings_for("Law & Order")
        self.assertEqual([a["title"] for a in airings], ["Ep A", "Ep B"])
        self.assertEqual((airings[0]["season_number"], airings[0]["episode_number"]), (2, 5))



class StreamingRecordTests(unittest.TestCase):
    """Recording a streaming show: PATCH /guide/<cloud airing ID> {"scheduled": true}, the request
    Tablo's own app sends (captured 2026-10-21). The Tablo is faked here."""

    def setUp(self):
        db.init_db()
        streaming.save(streaming.rows_from_grid(GRID))
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.sent = []
        self.states = {}

        async def request_local(method, path, body=""):
            # Like the Tablo: /guide/LH-... objects only with ?lh
            if method == "POST" and path.startswith("/batch"):
                if path != "/batch?lh":
                    return httpx.Response(200, json={"error": {"description": "Endpoint not found"}})
                return httpx.Response(200, json={p: {"schedule": {"state": self.states.get(p, "none")}} for p in json.loads(body)})
            self.sent.append((method, path, json.loads(body) if body else None))
            if not path.endswith("?lh"):
                return httpx.Response(404, json={"error": {"description": "Endpoint not found"}})
            self.states[path[:-len("?lh")]] = "scheduled" if json.loads(body)["scheduled"] else "none"
            return httpx.Response(200, json={})

        for p in (mock.patch.object(tablo_manager, "request_local", new=request_local),
                  mock.patch.object(type(tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True))):
            p.start()
            self.addCleanup(p.stop)

    def airing_id(self, show):
        return streaming.airings_for(show)[-1]["id"]

    def record(self, airing_id, on=True):
        return self.client.post("/api/streaming/record", json={"airing_id": airing_id, "scheduled": on},
                                headers={"X-TabloView": "1"})

    def test_record_and_cancel(self):
        aid = self.airing_id("Law & Order")
        r = self.record(aid)
        self.assertEqual(r.json()["schedule_state"], "scheduled")
        self.assertEqual(self.sent, [("PATCH", f"/guide/{aid}?lh", {"scheduled": True})])
        self.assertEqual(self.record(aid, on=False).json()["schedule_state"], "none")

    def test_the_airings_list_says_which_are_set_to_record(self):
        aid = self.airing_id("Law & Order")
        self.record(aid)
        airings = self.client.get("/api/streaming/shows/Law%20%26%20Order/airings").json()["airings"]
        self.assertEqual({a["id"]: a["schedule_state"] for a in airings}[aid], "scheduled")

    def test_channels_the_tablo_may_not_record_are_refused(self):
        r = self.record(self.airing_id("Tiny House Hunters"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.sent, [])

    def test_only_airings_in_the_streaming_guide(self):
        self.assertEqual(self.record("LH-not-a-real-airing").status_code, 404)
        self.assertEqual(self.record("/recordings/series/episodes/1").status_code, 400)
        self.assertEqual(self.sent, [])



class StreamingUpcomingTests(unittest.TestCase):
    """Streaming recordings appear in Home's Recording soon and Scheduled's Upcoming recordings, from
    the Tablo's own upcoming list, without counting against the antenna tuners."""

    def setUp(self):
        db.init_db()
        streaming.save(streaming.rows_from_grid(GRID))
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))

    def test_listed_in_time_order_and_never_a_conflict(self):
        from app.routes import guide, live
        law = streaming.airings_for("Law & Order")[-1]
        start = datetime.fromisoformat(law["air_datetime"].replace("Z", "+00:00"))
        antenna = {"path": "/guide/series/episodes/1", "series_path": "/guide/series/1", "show_title": "Antenna Show",
                   "episode_title": "", "season_number": 1, "episode_number": 1,
                   "air_datetime": (start + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%MZ"), "duration": 3600,
                   "channel_call_sign": "WAAA", "channel_network": "CBS", "qualifiers": [], "is_new": False,
                   "is_premiere": False, "schedule_state": "scheduled"}
        with mock.patch.object(guide, "get_upcoming_recordings", return_value=[antenna]),              mock.patch.object(streaming, "scheduled_airing_ids", new=mock.AsyncMock(return_value={law["id"], "LH-other"})),              mock.patch.object(live, "model_tuner_count", new=mock.AsyncMock(return_value=1)),              mock.patch.object(type(tablo_manager), "is_authenticated", new=mock.PropertyMock(return_value=True)):
            data = self.client.get("/api/guide/upcoming", headers={"X-TabloView": "1"}).json()
        titles = [r["show_title"] for r in data["recordings"]]
        self.assertEqual(titles, ["Law & Order", "Antenna Show"])  # by start time
        first = data["recordings"][0]
        self.assertTrue(first["streaming"])
        self.assertEqual((first["path"], first["channel_call_sign"]), (law["id"], "ION"))
        self.assertEqual(data["conflicts"], [])  # one antenna tuner, one antenna recording

    def test_in_the_calendar_too(self):
        from app.routes import guide
        law = streaming.airings_for("Law & Order")[-1]
        with mock.patch.object(guide, "get_upcoming_recordings", return_value=[]),              mock.patch.object(streaming, "scheduled_airing_ids", new=mock.AsyncMock(return_value={law["id"]})):
            ics = self.client.get("/api/guide/upcoming.ics", headers={"X-TabloView": "1"}).text
        self.assertIn("SUMMARY:Law & Order", ics)
        self.assertIn("ION", ics)


if __name__ == "__main__":
    unittest.main()
