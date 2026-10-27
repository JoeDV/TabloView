"""Streaming (FAST) channel listings, for the Guide's Streaming tab: a week of airings from Tablo's
cloud guide grid (the Tablo's own guide only covers antenna channels), kept in the database and
refreshed every few hours. Nothing here asks the Tablo itself.

Shows are put in a category from their kind (movie, sports event) and their genres; shows with no
genres (about one in ten) take their channel's usual category."""

import asyncio
import json
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


from . import redact
from .database import get_connection, get_sync_meta, set_sync_meta

DAYS = 8  # today and the next 7; the cloud has little beyond that
REFRESH_SECONDS = 6 * 3600
WORKER_INTERVAL = 60
CLOUD_HOST = "https://lighthousetv.ewscloud.com"
USER_AGENT = "Tablo-FAST/2.0.0 (Mobile; iPhone; iOS 16.6)"

# (id, label, genres): checked in this order after movies and sports; a show goes in the first
# category one of its genres (most common first) belongs to
CATEGORIES = [
    ("news", "News", {"news", "noticias", "bus./financial", "weather", "public affairs", "politics", "newsmagazine"}),
    ("reality", "Reality & lifestyle", {"reality", "house/garden", "home improvement", "cooking", "food", "fashion",
                                        "travel", "shopping", "auto", "consumer", "how-to", "outdoors", "fishing",
                                        "hunting", "game show", "competition reality", "arts/crafts", "art",
                                        "self improvement", "community"}),
    ("documentary", "Documentary & science", {"documentary", "science", "technology", "nature", "history",
                                              "animals", "biography", "educational", "environment", "paranormal"}),
    ("drama", "Drama & crime", {"drama", "crime", "crime drama", "mystery", "thriller", "romance", "soap",
                                "suspense", "law", "medical", "true crime"}),
    ("comedy", "Comedy", {"comedy", "sitcom", "comedy drama", "standup"}),
    ("entertainment", "Talk & entertainment", {"talk", "entertainment", "entretenimiento", "music", "variety",
                                                "interview", "awards", "musical", "special", "tvshow", "anthology",
                                                "gaming"}),
    ("action", "Action & sci-fi", {"action", "adventure", "science fiction", "horror", "western", "fantasy",
                                   "anime", "war", "martial arts"}),
    ("kids", "Kids & family", {"children", "animated", "family", "kids"}),
]
LABELS = {"movies": "Movies", "sports": "Sports", **{c: label for c, label, _ in CATEGORIES}, "other": "Other"}
ORDER = ["news", "sports", "movies", "reality", "documentary", "drama", "comedy", "action", "entertainment", "kids", "other"]
# The cloud tags games by the sport itself (boxing, pickleball...) as often as with "sports"
SPORTS = {"sport", "boxing", "mixed martial arts", "basketball", "pickleball", "soccer", "poker", "football",
          "pro wrestling", "surfing", "triathlon", "mountain biking", "baseball", "golf", "hockey", "bull riding",
          "snowboarding", "skiing", "marathon", "darts", "weightlifting", "card games", "tennis", "racing",
          "motorsports", "auto racing", "rodeo", "volleyball", "softball", "wrestling", "cycling", "fishing tournament"}

# Channels whose listings carry no genres at all: their name says what they are
CHANNEL_HINTS = [("sport", "sports"), ("team usa", "sports"), ("bein", "sports"), ("nascar", "sports"),
                 ("poker", "sports"), ("tennis", "sports"), ("stadium", "sports"),
                 ("news", "news"), ("weather", "news"), ("bloomberg", "news"),
                 ("food", "reality"), ("tasty", "reality"), ("cook", "reality"), ("home", "reality"),
                 ("design", "reality"), ("whisperer", "reality"),
                 ("movie", "movies"), ("rom com", "movies"), ("cinema", "movies"), ("flix", "movies"),
                 ("crime", "drama"), ("court", "drama"), ("mystery", "drama"),
                 ("nosey", "entertainment"), ("confess", "entertainment"), ("lati", "entertainment"),
                 ("country", "entertainment"), ("music", "entertainment")]


def channel_hint(name: str) -> Optional[str]:
    lower = (name or "").lower()
    return next((cat for word, cat in CHANNEL_HINTS if word in lower), None)


status: Dict[str, Any] = {"refreshing": False, "error": None}
_shows_cache: Dict[str, Any] = {"key": None, "shows": []}


def category(kinds: Counter, genres: Counter) -> Optional[str]:
    """The show's category, or None when its genres don't say (its channel's category is used then).
    A "movie" with no genres isn't trusted: the cloud calls clip shows feature films too."""
    if kinds.get("sportEvent") or any(g in SPORTS or "sport" in g for g in genres):
        return "sports"
    if not genres:
        return None
    if kinds.get("movieAiring", 0) >= max(1, sum(kinds.values()) / 2):
        return "movies"
    for genre, _ in genres.most_common():
        for cid, _label, members in CATEGORIES:
            if genre in members:
                return cid
    return "other"


def _image(airing: Dict[str, Any]) -> str:
    by_kind = {i.get("kind"): i.get("url") for i in airing.get("images") or [] if i.get("url")}
    for kind in ("coverLarge", "background", "backdropLarge", "stillLarge", "coverSmall", "poster"):
        if by_kind.get(kind):
            return by_kind[kind]
    return ""


def rows_from_grid(grid: List[Dict[str, Any]]) -> List[tuple]:
    """Streaming channels' airings from one day of the cloud guide grid, as stream_airings rows."""
    rows = []
    for item in grid:
        ch = item.get("channel") or {}
        if ch.get("kind") != "ott":
            continue  # antenna channels are in the Tablo's own guide
        ott = ch.get("ott") or {}
        for a in item.get("airings") or []:
            show = a.get("show") or {}
            ep = a.get("episode") or {}
            season = (ep.get("season") or {}).get("number") if isinstance(ep.get("season"), dict) else None
            rows.append((
                a.get("identifier"), show.get("identifier") or a.get("title"), show.get("title") or a.get("title") or "",
                a.get("title") or "", a.get("kind") or "", season or 0, ep.get("episodeNumber") or 0,
                a.get("datetime") or "", int(a.get("duration") or 0), a.get("description") or "",
                json.dumps([str(g).lower() for g in a.get("genres") or []]), _image(a),
                json.dumps(a.get("qualifierTags") or []),
                ch.get("identifier"), ch.get("name") or ott.get("callSign") or "", json.dumps(ch.get("logos") or []),
                1 if ott.get("canRecord") else 0, ott.get("channelPartner") or "",
                f"{ott['major']}.{ott.get('minor') or 0}" if ott.get("major") else "",
            ))
    return rows


async def _fetch_day(device, day: str) -> List[Dict[str, Any]]:
    from .tablo_client import tablo_manager
    url = f"{CLOUD_HOST}/api/v2/account/{device.lighthouse_token}/guide/grid/?day={day}&limit=200"
    r = await tablo_manager._http.get(url, headers={"Authorization": f"Bearer {device.account_token}",
                                                    "Lighthouse": device.lighthouse_token, "User-Agent": USER_AGENT}, timeout=20)
    # Not raise_for_status(): its message repeats the address, which carries the account's token
    if r.status_code != 200:
        raise RuntimeError(f"Tablo's guide service answered {r.status_code} for {day}")
    return r.json().get("grid") or []


def save(rows: List[tuple]) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM stream_airings")
        conn.executemany("""
            INSERT OR REPLACE INTO stream_airings (id, show_id, show_title, title, kind, season_number,
                episode_number, air_datetime, duration, description, genres, image, tags, channel_identifier,
                channel_name, channel_logos, can_record, partner, channel_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


async def refresh() -> int:
    """Load today and the next week from the cloud (one request per day). Returns airings saved."""
    from .tablo_client import tablo_manager
    if status["refreshing"] or not tablo_manager.is_authenticated:
        return 0
    status["refreshing"] = True
    try:
        rows: List[tuple] = []
        today = date.today()
        for n in range(DAYS):
            day = (today + timedelta(days=n)).isoformat()
            grid = await _fetch_day(tablo_manager.device, day)
            rows += rows_from_grid(grid)
            await asyncio.sleep(1)
        await asyncio.to_thread(save, rows)
        set_sync_meta("last_streaming_sync", datetime.now(timezone.utc).isoformat())
        status["error"] = None
        print(f"[Streaming] Saved {len(rows)} streaming airings for the next {DAYS} days")
        return len(rows)
    except Exception as e:
        status["error"] = redact.scrub(str(e))
        print(f"[Streaming] Couldn't load the streaming guide: {e}")
        return 0
    finally:
        status["refreshing"] = False


def last_refresh() -> Optional[str]:
    return get_sync_meta("last_streaming_sync")


def due() -> bool:
    last = last_refresh()
    if not last:
        return True
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() > REFRESH_SECONDS
    except ValueError:
        return True


async def worker_loop() -> None:
    from .tablo_client import tablo_manager
    while True:
        try:
            if tablo_manager.is_authenticated and due():
                await refresh()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Streaming] {e}")
        await asyncio.sleep(WORKER_INTERVAL)


def _future_airings(where: str = "", params: tuple = ()) -> List[Dict[str, Any]]:
    """Airings that haven't finished, optionally narrowed (reading all ~20,000 took half a second)."""
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT * FROM stream_airings
            WHERE datetime(air_datetime, '+' || duration || ' seconds') > datetime('now') {where}
            ORDER BY air_datetime
        """, params).fetchall()
    return [dict(r) for r in rows]


def shows() -> List[Dict[str, Any]]:
    """One entry per show with an airing still to come: its category, next airing, channels, and
    whether any of its channels can be recorded on the Tablo. Rebuilt when the data changes or a
    show's next airing has passed."""
    key = (last_refresh(), int(time.time() // 300))
    if _shows_cache["key"] == key:
        return _shows_cache["shows"]
    now = datetime.now(timezone.utc)
    by_show: Dict[str, Dict[str, Any]] = {}
    for a in _future_airings():
        s = by_show.get(a["show_id"])
        if not s:
            s = by_show[a["show_id"]] = {
                "show_id": a["show_id"], "title": a["show_title"], "image": a["image"], "next": a,
                "channels": [], "airings": 0, "can_record": False, "on_now": False,
                "_kinds": Counter(), "_genres": Counter(),
            }
        s["airings"] += 1
        s["_kinds"][a["kind"]] += 1
        s["_genres"].update(json.loads(a["genres"] or "[]"))
        s["image"] = s["image"] or a["image"]
        s["can_record"] = s["can_record"] or bool(a["can_record"])
        if a["channel_name"] not in s["channels"]:
            s["channels"].append(a["channel_name"])
        try:
            start = datetime.fromisoformat(a["air_datetime"].replace("Z", "+00:00"))
            if start <= now:
                s["on_now"] = True
        except ValueError:
            pass
    # Each channel's usual category, for its shows with no genres
    by_channel: Dict[str, Counter] = {}
    for s in by_show.values():
        s["category"] = category(s.pop("_kinds"), s.pop("_genres"))
        if s["category"]:
            by_channel.setdefault(s["next"]["channel_identifier"], Counter())[s["category"]] += s["airings"]
    out = []
    for s in by_show.values():
        if not s["category"]:
            usual = by_channel.get(s["next"]["channel_identifier"])
            s["category"] = (usual.most_common(1)[0][0] if usual
                             else channel_hint(s["next"]["channel_name"]) or "other")
        n = s.pop("next")
        s["next_airing"] = {"datetime": n["air_datetime"], "duration": n["duration"], "title": n["title"],
                            "channel_identifier": n["channel_identifier"], "channel_name": n["channel_name"],
                            "logos": json.loads(n["channel_logos"] or "[]")}
        out.append(s)
    out.sort(key=lambda s: (not s["on_now"], s["next_airing"]["datetime"], s["title"].lower()))
    _shows_cache.update(key=key, shows=out)
    return out


_upcoming: Dict[str, Any] = {"at": 0.0, "ids": set()}
UPCOMING_SECONDS = 60


async def scheduled_airing_ids(fresh: bool = False) -> set:
    """IDs of the airings the Tablo will record (antenna and streaming): the list Tablo's own app
    shows as upcoming (/views/guide/upcoming, day by day). Kept for a minute; the Live TV grid asks
    every time it loads."""
    from .tablo_client import tablo_manager
    if not tablo_manager.is_authenticated:
        return set()
    if not fresh and time.time() - _upcoming["at"] < UPCOMING_SECONDS:
        return _upcoming["ids"]
    try:
        resp = await tablo_manager.request_local("GET", "/views/guide/upcoming?lh")
        days = resp.json() if resp.status_code == 200 else None
        if isinstance(days, list):
            _upcoming.update(at=time.time(), ids={i for d in days for i in (d.get("contents") or [])})
    except Exception as e:
        print(f"[Streaming] Couldn't read the Tablo's upcoming recordings: {e}")
    return _upcoming["ids"]


def forget_upcoming() -> None:
    _upcoming["at"] = 0.0


def upcoming_recordings(ids: set) -> List[Dict[str, Any]]:
    """The streaming airings among these (the Tablo's upcoming list) that haven't finished, shaped
    like database.get_upcoming_recordings rows so Scheduled and Home list them with the rest."""
    if not ids:
        return []
    out = []
    ids = sorted(ids)
    found = [a for n in range(0, len(ids), 500)
             for a in _future_airings(f"AND id IN ({','.join('?' * len(ids[n:n + 500]))})", tuple(ids[n:n + 500]))]
    for a in sorted(found, key=lambda a: a["air_datetime"]):
        tags = json.loads(a["tags"] or "[]")
        out.append({
            "path": a["id"], "airing_id": a["id"], "streaming": True, "show_id": a["show_id"],
            "series_path": None, "show_title": a["show_title"],
            "episode_title": a["title"] if a["title"] != a["show_title"] else "",
            "season_number": a["season_number"], "episode_number": a["episode_number"],
            "air_datetime": a["air_datetime"], "duration": a["duration"],
            "channel_call_sign": a["channel_name"], "channel_network": "", "channel_identifier": a["channel_identifier"],
            "channel_number": a["channel_number"] or "", "channel_logos": json.loads(a["channel_logos"] or "[]"),
            "qualifiers": tags, "is_new": "new" in tags, "is_premiere": "premiere" in tags,
            "schedule_state": "scheduled", "cover_url": a["image"], "backdrop_url": None, "schedule_rule": None,
        })
    return out


def airing(airing_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM stream_airings WHERE id = ?", (airing_id,)).fetchone()
    return dict(row) if row else None


def airings_for(show_id: str) -> List[Dict[str, Any]]:
    return _future_airings("AND show_id = ?", (show_id,))
