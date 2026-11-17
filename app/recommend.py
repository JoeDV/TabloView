"""Guide → For you: shows on the antenna channels in the next two weeks that aren't being recorded,
picked to suit the series that are (only those: nothing about what's watched).

With the user's Anthropic key (Settings → Playback, the one that finds commercials) Claude picks them: it
knows the shows themselves (9-1-1: Nashville is a 9-1-1 spinoff; Andy Griffith reruns aren't a new
sitcom), where the guide's genres only say "Sitcom" or "Drama". It's asked only when For you is opened
and the last picks are out of date: the recorded series changed, a week went by, or fewer than
MIN_LEFT of them are still airing unrecorded (or New picks is pressed). About 5 cents a time
(2026-11-17: 33 recorded series, 358 airing; 9,065 tokens sent, 535 returned).

Without a key, or if Claude can't be reached: by genre. Each genre counts for less the more of the guide
has it, a show is scored by its three closest recorded series, and one with no new episodes coming
counts for less.

Shows with a premiere coming that suit what's recorded go first, under their own heading (a premiere is the
easiest time to start one): a new series, then a new season, the soonest first. One-off specials marked as
premieres (an awards show) are only that.
"""

import json
import math
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .config import DATA_DIR
from .database import get_connection, get_guide_shows, get_scheduled_guide_shows

PICKS = 12
MIN_LEFT = 6
FRESH_FOR = timedelta(days=7)
CACHE_FILE = DATA_DIR / "recommendations.json"
# Not shows to suggest, unless something recorded is one too
NOT_SUGGESTED = {"news", "paid programming", "shopping", "religious", "public affairs", "consumer", "talk",
                 "children", "educational"}
RERUNS_ONLY = 0.6
PREMIERE_REACH = 3 * PICKS  # by genre, a premiering show this far down the list still joins the picks  # a show with no new episodes in the guide, by genre: this much of its score

_lock = threading.Lock()


def _genres(show: Dict) -> List[str]:
    return [str(g).lower() for g in show.get("genres") or []]


def _new_counts() -> Dict[str, int]:
    """Per series, how many of its airings in the guide are new episodes."""
    with get_connection() as conn:
        return {p: n for p, n in conn.execute(
            "SELECT series_path, SUM(is_new = 1) FROM guide_airings GROUP BY series_path").fetchall()}


PREMIERE_ORDER = {"series": 0, "season": 1, "special": 2}


def _premieres() -> Dict[str, Dict[str, str]]:
    """Per series, its first premiere still to come: {"kind": "series" | "season" | "special", "datetime"}.
    The guide marks a new series "series_premiere" or "premiere" (season 1, episode 1), a new season
    "season_premiere", and a one-off's first airing "premiere"."""
    out: Dict[str, Dict[str, str]] = {}
    with get_connection() as conn:
        rows = conn.execute("""SELECT series_path, qualifiers, season_number, episode_number, air_datetime FROM guide_airings
                               WHERE is_premiere = 1 AND series_path != ''
                                 AND datetime(air_datetime, '+' || duration || ' seconds') > datetime('now')
                               ORDER BY air_datetime""").fetchall()
    for path, qualifiers, season, episode, when in rows:
        try:
            marks = set(json.loads(qualifiers or "[]"))
        except ValueError:
            marks = set()
        if "series_premiere" in marks or ("premiere" in marks and season == 1 and episode == 1):
            kind = "series"
        elif "season_premiere" in marks:
            kind = "season"
        else:
            kind = "special"
        if path not in out or PREMIERE_ORDER[kind] < PREMIERE_ORDER[out[path]["kind"]]:
            out[path] = {"kind": kind, "datetime": when}
    return out


def premieres_first(found: List[Dict]) -> List[Dict]:
    """Shows with a new series or season premiering first (series, then season, soonest first), the rest
    in the order they were picked."""
    def key(i_s):
        i, s = i_s
        p = s.get("premiere")
        if p and p["kind"] in ("series", "season"):
            return (0, PREMIERE_ORDER[p["kind"]], p["datetime"], i)
        return (1, 0, "", i)
    return [s for _, s in sorted(enumerate(found), key=key)]


def shows() -> Tuple[List[Dict], List[Dict]]:
    """(the recorded series, the series airing in the next two weeks that aren't recorded and could be suggested)."""
    liked = [s for s in get_scheduled_guide_shows() if s.get("category") == "series"]
    liked_genres = {g for s in liked for g in _genres(s)}
    new = _new_counts()
    premieres = _premieres()
    candidates = []
    for s in get_guide_shows(category="series", rule="unscheduled", sort_by="soonest", limit=500):
        if any(g in NOT_SUGGESTED and g not in liked_genres for g in _genres(s)):
            continue
        s.pop("raw_json", None)
        s["new_episodes"] = int(new.get(s["path"]) or 0)
        s["premiere"] = premieres.get(s["path"])
        candidates.append(s)
    return liked, candidates


def by_genre(liked: List[Dict], candidates: List[Dict], every_genre: List[List[str]]) -> List[Dict]:
    """The best PICKS of the candidates by genre, each with "because": the recorded series most like it.
    every_genre: the genres of every show in the guide, to weigh how common each genre is."""
    df = Counter(g for gs in every_genre for g in set(gs))
    n = max(1, len(every_genre))
    idf = {g: math.log(n / (1 + c)) for g, c in df.items()}

    def vector(gs: List[str]) -> Dict[str, float]:
        v = {g: max(0.0, idf.get(g, math.log(n))) for g in gs}
        size = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / size for g, x in v.items()}
    recorded = [(s["title"], vector(_genres(s))) for s in liked]
    scored = []
    for s in candidates:
        mine = vector(_genres(s))
        if not mine:
            continue
        near = sorted(((sum(w * v.get(g, 0.0) for g, w in mine.items()), t) for t, v in recorded), reverse=True)
        score = sum(x for x, _ in near[:3]) * (1.0 if s.get("new_episodes") else RERUNS_ONLY)
        if score <= 0:
            continue
        because = [t for x, t in near[:2] if x > 0 and x >= 0.5 * near[0][0]]
        scored.append((score, s["title"].lower(), {**s, "because": because, "why": None}))
    scored.sort(key=lambda x: (-x[0], x[1]))
    picks = [s for _, _, s in scored[:PICKS]]
    # A premiere a little further down still makes it: within the best PREMIERE_REACH
    picks += [s for _, _, s in scored[PICKS:PREMIERE_REACH]
              if s.get("premiere") and s["premiere"]["kind"] in ("series", "season")]
    return premieres_first(picks)


PROMPT = """These are the TV series a household has set their DVR to record:
{liked}

These series air on their antenna channels over the next two weeks and aren't being recorded:
{candidates}

Pick the {picks} from the second list this household is most likely to enjoy, best first, judging by what \
they record (the shows themselves, not just the genres). Prefer shows with new episodes. For each, one \
short sentence saying why, naming the recorded shows it's like. Use the titles exactly as listed. A series or season premiere is the easiest time to start a show: include any premiering show that suits them, as well as the {picks}."""

SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "why": {"type": "string"}},
        "required": ["title", "why"], "additionalProperties": False}}},
    "required": ["picks"], "additionalProperties": False,
}


def _line(s: Dict) -> str:
    genres = ", ".join(s.get("genres") or []) or "no genre"
    premiere = (s.get("premiere") or {}).get("kind")
    marks = {"series": " [series premiere]", "season": " [season premiere]"}.get(premiere, "")
    return f"- {s['title']} ({genres}){' [new episodes]' if s.get('new_episodes') else ''}{marks}"


def ask_claude(key: str, liked: List[Dict], candidates: List[Dict]) -> List[Dict[str, str]]:
    """Claude's picks as [{"title", "why"}]. Raises on any failure. Blocking."""
    import anthropic
    from .claude_ads import MODEL, PRICE_IN, PRICE_OUT
    client = anthropic.Anthropic(api_key=key, timeout=120)
    prompt = PROMPT.format(liked="\n".join(_line(s) for s in liked),
                           candidates="\n".join(_line(s) for s in candidates), picks=PICKS)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Claude's answer stopped ({response.stop_reason})")
    u = response.usage
    print(f"[For you] Claude: {u.input_tokens} tokens sent, {u.output_tokens} returned, "
          f"about ${(u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6:.3f}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["picks"]


def matched(picks: List[Dict[str, str]], candidates: List[Dict]) -> List[Dict[str, str]]:
    """Claude's picks that are candidates (by title, any case), once each, with a real reason (one
    test answer's last pick said only "placeholder"): [{"path", "why"}]."""
    by_title = {}
    for s in candidates:
        by_title.setdefault(s["title"].strip().lower(), s)
    out, seen = [], set()
    for p in picks:
        s = by_title.get(str(p.get("title", "")).strip().lower())
        why = str(p.get("why") or "").strip()
        if not s or s["path"] in seen or len(why) < 15 or "placeholder" in why.lower():
            continue
        seen.add(s["path"])
        out.append({"path": s["path"], "why": why})
    return out


def _load() -> Optional[Dict]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(data: Dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError as e:
        print(f"[For you] Couldn't keep the picks: {e}")


def still_good(cached: Optional[Dict], liked_paths: List[str], candidate_paths: set, now: datetime) -> bool:
    """Whether the last picks can be shown again instead of asking Claude."""
    if not cached or cached.get("liked") != liked_paths:
        return False
    try:
        at = datetime.fromisoformat(cached["at"])
    except (KeyError, TypeError, ValueError):
        return False
    if now - at > FRESH_FOR:
        return False
    return sum(1 for p in cached.get("picks") or [] if p.get("path") in candidate_paths) >= MIN_LEFT


def recommendations(refresh: bool = False) -> Dict:
    """For the Guide's For you: {"by": "claude" | "genre", "shows": [guide show + "why" / "because"],
    "error": why Claude couldn't be asked, or None}. Blocking (Claude): run it in a thread."""
    from .claude_ads import api_key
    with _lock:
        liked, candidates = shows()
        if not liked:
            return {"by": None, "shows": [], "error": None, "recorded": 0}
        by_path = {s["path"]: s for s in candidates}
        liked_paths = sorted(s["path"] for s in liked)
        key = api_key()
        error = None
        if key:
            cached = _load()
            now = datetime.now(timezone.utc)
            if refresh or not still_good(cached, liked_paths, set(by_path), now):
                try:
                    picks = matched(ask_claude(key, liked, candidates), candidates)
                    if picks:
                        cached = {"liked": liked_paths, "at": now.isoformat(), "picks": picks}
                        _save(cached)
                except Exception as e:
                    print(f"[For you] Claude couldn't pick: {e}")
                    error = str(e)[:300]
            if cached and cached.get("liked") == liked_paths:
                found = [{**by_path[p["path"]], "why": p["why"], "because": []}
                         for p in cached.get("picks") or [] if p.get("path") in by_path]
                if found:
                    return {"by": "claude", "shows": premieres_first(found), "error": error, "recorded": len(liked),
                            "picked_at": cached.get("at")}
        with get_connection() as conn:
            every = [[str(g).lower() for g in json.loads(r[0] or "[]")] for r in conn.execute("SELECT genres FROM guide_shows")]
        return {"by": "genre", "shows": by_genre(liked, candidates, every), "error": error, "recorded": len(liked)}
