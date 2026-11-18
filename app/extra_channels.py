"""Channels from outside the Tablo: an M3U playlist (and optionally an XMLTV guide) the user adds in
Settings → Live TV. They join Live TV as a third group beside Antenna and Streaming, play straight
from their own web address (no Tablo tuner), and can't be recorded.

M3U: "#EXTINF:-1 tvg-id=".." tvg-logo=".." tvg-chno=".." group-title="..",Name" followed by the
stream's address. XMLTV: <channel id> and <programme start stop channel> with <title>, <sub-title>,
<desc>, <category>, <icon src>, <episode-num system="xmltv_ns">.
"""
import asyncio
import gzip
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .settings import load_settings, save_settings

PLAYLIST_SECONDS = 3600  # lists change rarely; read again after an hour
GUIDE_SECONDS = 12 * 3600  # guide files are rebuilt about once a day (Tubi's list: a daily GitHub job)
GUIDE_HOURS_BEFORE, GUIDE_HOURS_AFTER = 3, 30  # listings kept around now (guide files cover days)
MAX_DOWNLOAD = 200 * 1024 * 1024
PREFIX = "x-"  # channel ids: x-<10 hex>, from the stream's address
# A provider's whole list can run to hundreds of thousands of entries (a forum user's: 386,496), and
# most of them are movies and series episodes: those are left out (Xtream's /movie/ and /series/
# addresses, or a video file). Above IN_GUIDE channels the guide gets only the favorites, and the
# More tab asks for PAGE at a time (page()), searched on the server
VOD = re.compile(r"/(movie|movies|series)/|\.(mp4|mkv|avi|mov|m4v|wmv|flv|webm|mpg|mpeg)(\?|$)", re.I)
IN_GUIDE = 3000
PAGE = 200

_playlist: Dict[str, Any] = {"url": None, "at": 0.0, "channels": [], "error": None}
_guide: Dict[str, Any] = {"url": None, "at": 0.0, "by_channel": {}, "error": None, "task": None}
_lock = asyncio.Lock()

_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def is_extra(channel_id: Optional[str]) -> bool:
    return bool(channel_id) and str(channel_id).startswith(PREFIX)


def parse_m3u(text: str, stats: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """[{id, name, url, logo, tvg_id, number, group}] in the playlist's order (stats["skipped"]: how
    many movies and series episodes were left out)."""
    out: List[Dict[str, Any]] = []
    info: Optional[Dict[str, Any]] = None
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            head, _, name = line.partition(",")
            # (a comma inside a quoted attribute: take the name after the last quote)
            if head.count('"') % 2:
                q = line.rfind('"')
                head, name = line[:q + 1], line[q + 1:].partition(",")[2]
            attrs = dict(_ATTR.findall(head))
            info = {"name": (name.strip() or attrs.get("tvg-name") or "").strip(), "attrs": attrs}
        elif line.startswith("#"):
            continue
        elif info is not None:
            if not re.match(r"https?://", line, re.I) or VOD.search(line):
                if stats is not None and VOD.search(line):
                    stats["skipped"] = stats.get("skipped", 0) + 1
                info = None
                continue
            cid = PREFIX + hashlib.sha1(line.encode()).hexdigest()[:10]
            if cid not in seen:
                seen.add(cid)
                a = info["attrs"]
                num = a.get("tvg-chno") or a.get("channel-number") or ""
                out.append({"id": cid, "name": info["name"] or a.get("tvg-id") or "Channel", "url": line,
                            "logo": a.get("tvg-logo") or None, "tvg_id": a.get("tvg-id") or a.get("channel-id") or "",
                            "number": num, "group": a.get("group-title") or ""})
            info = None
    return out


def _read_playlist(data: bytes) -> Tuple[List[Dict[str, Any]], int]:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    stats: Dict[str, int] = {}
    return parse_m3u(data.decode("utf-8", errors="replace"), stats), stats.get("skipped", 0)


def _xmltv_time(s: str) -> Optional[datetime]:
    """'20261106180000 +0000' (offset optional) -> aware UTC datetime."""
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", s or "")
    if not m:
        return None
    dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    delta = timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
    return (dt - delta if off[0] == "+" else dt + delta).replace(tzinfo=timezone.utc)


def parse_xmltv(data: bytes, wanted: set, now: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
    """tvg-id -> airings (Live TV's airing fields) near now, for the channels in `wanted`."""
    now = now or datetime.now(timezone.utc)
    lo, hi = now - timedelta(hours=GUIDE_HOURS_BEFORE), now + timedelta(hours=GUIDE_HOURS_AFTER)
    import io
    src = gzip.GzipFile(fileobj=io.BytesIO(data)) if data[:2] == b"\x1f\x8b" else io.BytesIO(data)
    by: Dict[str, List[Dict[str, Any]]] = {}
    for _, el in ET.iterparse(src, events=("end",)):
        if el.tag != "programme":
            if el.tag == "channel":
                el.clear()
            continue
        ch = el.get("channel") or ""
        start, stop = _xmltv_time(el.get("start", "")), _xmltv_time(el.get("stop", ""))
        if ch in wanted and start and stop and stop > lo and start < hi:
            title = (el.findtext("title") or "").strip()
            season = episode = None
            for en in el.findall("episode-num"):
                if en.get("system") == "xmltv_ns":
                    parts = (en.text or "").split(".")
                    try:
                        season = int(parts[0].split("/")[0]) + 1 if parts[0].strip() else None
                        episode = int(parts[1].split("/")[0]) + 1 if len(parts) > 1 and parts[1].strip() else None
                    except ValueError:
                        pass
            icon = el.find("icon")
            genres = [c.text.strip() for c in el.findall("category") if c.text]
            by.setdefault(ch, []).append({
                "path": f"/channel/{ch}/extra",  # (not an airing the Tablo could record)
                "series_path": None,
                "title": title, "show_title": title,
                "episode_title": (el.findtext("sub-title") or "").strip(),
                "description": (el.findtext("desc") or "").strip(),
                "season_number": season, "episode_number": episode,
                "air_datetime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration": int((stop - start).total_seconds()),
                "is_new": el.find("new") is not None, "is_primetime": False, "is_premiere": False,
                "qualifiers": [], "genres": genres, "category": "sports" if "Sports" in genres else "",
                "cover_url": icon.get("src") if icon is not None else None,
            })
        el.clear()
    for airings in by.values():
        airings.sort(key=lambda a: a["air_datetime"])
    return by


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True,
                                 headers={"User-Agent": "TabloView"}) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > MAX_DOWNLOAD:
                    raise ValueError("the file is too large")
            return bytes(buf)


async def channels(force: bool = False) -> List[Dict[str, Any]]:
    """The playlist's channels (read again after PLAYLIST_SECONDS, or now with force); [] when none is set."""
    url = (load_settings().get("extra_playlist_url") or "").strip()
    if not url:
        return []
    async with _lock:
        if force or _playlist["url"] != url or time.time() - _playlist["at"] > PLAYLIST_SECONDS:
            try:
                data = await _download(url)
                found, skipped = await asyncio.to_thread(_read_playlist, data)
                del data
                _playlist.update(url=url, at=time.time(), channels=found, skipped=skipped,
                                 error=None if found else "No channels found in that playlist")
                print(f"[Extra] {len(found)} channels from the playlist")
            except Exception as e:
                # Keep what we had; try again in a few minutes
                _playlist.update(url=url, at=time.time() - PLAYLIST_SECONDS + 300, error=str(e) or type(e).__name__)
                print(f"[Extra] Couldn't read the playlist: {e!r}")
    return _playlist["channels"] if _playlist["url"] == url else []


def _refresh_guide(url: str, wanted: set) -> None:
    """Read the guide in the background (big files take a while): the channel list doesn't wait."""
    task = _guide.get("task")
    if task and not task.done():
        return

    async def run():
        try:
            data = await _download(url)
            by = await asyncio.to_thread(parse_xmltv, data, wanted)
            _guide.update(url=url, at=time.time(), by_channel=by, error=None)
            print(f"[Extra] Guide: listings for {len(by)} of {len(wanted)} channels")
        except Exception as e:
            _guide.update(url=url, at=time.time() - GUIDE_SECONDS + 600, error=str(e) or type(e).__name__)
            print(f"[Extra] Couldn't read the guide: {e!r}")
    _guide["task"] = asyncio.get_running_loop().create_task(run())


def guide_for(chans: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    url = (load_settings().get("extra_guide_url") or "").strip()
    if not url:
        return {}
    if _guide["url"] != url or time.time() - _guide["at"] > GUIDE_SECONDS:
        _refresh_guide(url, {c["tvg_id"] for c in chans if c["tvg_id"]})
    return _guide["by_channel"] if _guide["url"] == url else {}


def find(channel_id: str) -> Optional[Dict[str, Any]]:
    return next((c for c in _playlist["channels"] if c["id"] == channel_id), None)


def find_same(old: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The same channel in a playlist read again, by its guide id or name (its address, and so its
    id, may have changed: lists like Tubi's are regenerated daily)."""
    for c in _playlist["channels"]:
        if (old["tvg_id"] and c["tvg_id"] == old["tvg_id"]) or (not old["tvg_id"] and c["name"] == old["name"]):
            return c
    return None


def _live_placeholder(c: Dict[str, Any], start_iso: str, hours: int) -> Dict[str, Any]:
    return {"path": f"/channel/{c['id']}/live", "series_path": None, "title": c["name"], "show_title": c["name"],
            "episode_title": "Live", "season_number": None, "episode_number": None, "air_datetime": start_iso,
            "duration": hours * 3600, "is_new": False, "is_primetime": False, "is_premiere": False, "qualifiers": []}


def key(c: Dict[str, Any]) -> str:
    """What favorites and hidden channels are kept by: the guide id, else the name (the address, and
    so the channel id, can change when the playlist is rebuilt)."""
    return c["tvg_id"] or f"name:{c['name']}"


def marks() -> Dict[str, set]:
    s = load_settings()
    return {"favorite": set(s.get("extra_favorites") or []), "hidden": set(s.get("extra_hidden") or []),
            "groups": set(s.get("extra_hidden_groups") or [])}


def is_hidden(c: Dict[str, Any], m: Dict[str, set]) -> bool:
    return key(c) in m["hidden"] or (bool(c["group"]) and c["group"] in m["groups"])


def hide_group(group: str, hidden: bool) -> Dict[str, bool]:
    """Hide a whole group of the playlist (a provider's list has hundreds: other countries, sports
    packages...), or show it again."""
    m = marks()
    (m["groups"].add if hidden else m["groups"].discard)(group)
    save_settings({"extra_hidden_groups": sorted(m["groups"])})
    return {"hidden": group in m["groups"]}


def mark(channel_key: str, favorite: Optional[bool] = None, hidden: Optional[bool] = None) -> Dict[str, bool]:
    """Favorite or hide a channel (kept by TabloView: the Tablo doesn't know these channels). Hiding
    one takes it out of the favorites too."""
    m = marks()
    if favorite is not None:
        (m["favorite"].add if favorite else m["favorite"].discard)(channel_key)
        if favorite:
            m["hidden"].discard(channel_key)
    if hidden is not None:
        (m["hidden"].add if hidden else m["hidden"].discard)(channel_key)
        if hidden:
            m["favorite"].discard(channel_key)
    save_settings({"extra_favorites": sorted(m["favorite"]), "extra_hidden": sorted(m["hidden"])})
    return {"favorite": channel_key in m["favorite"], "hidden": channel_key in m["hidden"]}


def channel_dict(c: Dict[str, Any], m: Optional[Dict[str, set]] = None) -> Dict[str, Any]:
    m = m if m is not None else marks()
    k = key(c)
    return {"channel_id": c["id"], "identifier": c["id"], "call_sign": c["name"], "major": 0, "minor": 0,
            "number": c["number"], "network": c["group"], "kind": "extra", "name": c["name"],
            "logo_url": c["logo"], "resolution": "HD", "can_record": False,
            "extra_key": k, "favorite": k in m["favorite"], "hidden": is_hidden(c, m),
            "group_hidden": bool(c["group"]) and c["group"] in m["groups"]}


def _row(c: Dict[str, Any], m: Dict[str, set], guide: Dict[str, List[Dict[str, Any]]],
         window_start: datetime, window_end: datetime, start_iso: str, hours: int) -> Dict[str, Any]:
    d = channel_dict(c, m)
    airings = []
    for a in guide.get(c["tvg_id"], []):
        s = datetime.fromisoformat(a["air_datetime"].replace("Z", "+00:00"))
        if s < window_end and s + timedelta(seconds=a["duration"]) > window_start:
            airings.append(a)
    d["airings"] = airings or [_live_placeholder(c, start_iso, hours)]
    return d


async def epg_rows(window_start: datetime, window_end: datetime, start_iso: str,
                   hours: int) -> Tuple[List[Dict[str, Any]], int]:
    """Live TV guide rows for the playlist's channels, in its order, and how many were left out: a
    playlist of more than IN_GUIDE gives only its favorites (the More tab pages through the rest)."""
    chans = await channels()
    guide = guide_for(chans)
    m = marks()
    picked = chans if len(chans) <= IN_GUIDE else [c for c in chans if key(c) in m["favorite"]]
    return [_row(c, m, guide, window_start, window_end, start_iso, hours) for c in picked], len(chans) - len(picked)


def _matches(c: Dict[str, Any], words: List[str], guide: Dict[str, List[Dict[str, Any]]]) -> bool:
    text = f"{c['name']} {c['group']}".lower()
    if all(w in text for w in words):
        return True
    shows = " ".join(a.get("title") or "" for a in guide.get(c["tvg_id"], [])).lower() if c["tvg_id"] else ""
    return bool(shows) and all(w in f"{text} {shows}" for w in words)


def groups(chans: List[Dict[str, Any]], m: Dict[str, set]) -> List[Dict[str, Any]]:
    """The playlist's groups in its order: [{name, count, hidden}]."""
    count: Dict[str, int] = {}
    for c in chans:
        count[c["group"]] = count.get(c["group"], 0) + 1
    return [{"name": g, "count": n, "hidden": g in m["groups"]} for g, n in count.items()]


async def page(window_start: datetime, window_end: datetime, start_iso: str, hours: int, q: str = "",
               offset: int = 0, limit: int = PAGE, with_hidden: bool = False, group: Optional[str] = None) -> Dict[str, Any]:
    """The More tab for a big playlist: the channels matching q (every word, in the name, group or
    the shows in its guide), in one group if asked (a hidden group shows when it's picked),
    PAGE at a time, how many match in all, and the playlist's groups."""
    chans = await channels()
    guide = guide_for(chans)
    m = marks()

    def pick():
        words = q.lower().split()

        def shown(c):
            if group is not None:
                return c["group"] == group and (with_hidden or key(c) not in m["hidden"])
            return with_hidden or not is_hidden(c, m)
        found = [c for c in chans if shown(c) and (not words or _matches(c, words, guide))]
        hidden = sum(1 for c in chans if (group is None or c["group"] == group) and key(c) in m["hidden"])
        return found, hidden, groups(chans, m)
    found, hidden, gs = await asyncio.to_thread(pick)
    res = {"rows": [_row(c, m, guide, window_start, window_end, start_iso, hours) for c in found[offset:offset + limit]],
           "total": len(found), "hidden": hidden}
    if not offset:  # (the list of groups comes with the first page only: a provider's can run to thousands)
        res["groups"] = gs
    return res


def status() -> Dict[str, Any]:
    """For Settings: how many channels, and what went wrong if anything."""
    return {"channels": len(_playlist["channels"]), "playlist_error": _playlist["error"],
            # A guide is matched by each channel's tvg-id: a playlist without them can't use one
            "with_guide_ids": sum(1 for c in _playlist["channels"] if c["tvg_id"]),
            "skipped": _playlist.get("skipped", 0),
            "guide_channels": len(_guide["by_channel"]), "guide_error": _guide["error"],
            "guide_loading": bool(_guide.get("task") and not _guide["task"].done())}
