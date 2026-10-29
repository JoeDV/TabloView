"""Plex: after an export, ask your Plex server to scan the folder it went into, so the episode shows up
in Plex right away. Plex usually doesn't notice new files on a network share by itself, so exports
otherwise wait for its next scheduled scan.

Sign-in is Plex's own: TabloView asks plex.tv for a PIN, you approve it on app.plex.tv, and TabloView
gets a token for your account (kept in settings.json, never shown or logged). The server's address and
its own token come from plex.tv's list of your servers; the first address that answers is kept.

Plex sees its library folders from where it runs (/volume1/Plex Videos/Plex TV on a NAS) while
TabloView writes through the network (\\\\NAS\\Plex Videos\\Plex TV), so an export is matched to a
library by the end of the paths, and the scan is asked for in Plex's own terms.

Once Plex has the new export (after_export waits for it): a show Plex matched to the wrong series is
matched to the right one, the recording's watched status or resume point is carried over, and for the
shows set to (settings "plex_archive_shows") the recording is deleted from the Tablo. The show pages
also mark recordings Plex has already (in_plex), and ask before exporting those again.
"""

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from .config import APP_VERSION
from .database import delete_episode, get_episode_by_id
from .settings import exports_dir, load_settings, save_settings

PLEX_TV = "https://plex.tv"
PRODUCT = "TabloView"
FIND_WAIT = 600  # how long to look for a new export in Plex, s (a big scan on a NAS takes minutes)
FIND_EVERY = 15
SHOW_CACHE_TTL = 300
LIBRARY_ID = "com.plexapp.plugins.library"
_show_cache: Dict[Tuple[str, str], Tuple[float, List[Dict[str, Any]]]] = {}


def client_id() -> str:
    """TabloView's id with Plex (one per install; Plex lists it under Authorized Devices)."""
    cid = load_settings().get("plex_client_id")
    if not cid:
        cid = uuid.uuid4().hex
        save_settings({"plex_client_id": cid})
    return cid


def _headers(token: Optional[str] = None) -> Dict[str, str]:
    h = {"X-Plex-Product": PRODUCT, "X-Plex-Version": APP_VERSION, "X-Plex-Client-Identifier": client_id(),
         "X-Plex-Device-Name": PRODUCT, "Accept": "application/json"}
    if token:
        h["X-Plex-Token"] = token
    return h


async def start_signin() -> Dict[str, Any]:
    """A PIN for Plex's sign-in page: open `url`, approve, then check_signin(id)."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{PLEX_TV}/api/v2/pins", params={"strong": "true"}, headers=_headers())
        r.raise_for_status()
        pin = r.json()
    url = "https://app.plex.tv/auth#?" + urlencode({"clientID": client_id(), "code": pin["code"],
                                                    "context[device][product]": PRODUCT})
    return {"id": pin["id"], "url": url}


async def check_signin(pin_id: int) -> bool:
    """True once the PIN was approved: the account token is saved, and the server too if there's
    only one (or one of the account's own)."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{PLEX_TV}/api/v2/pins/{int(pin_id)}", headers=_headers())
        r.raise_for_status()
        token = r.json().get("authToken")
    if not token:
        return False
    save_settings({"plex_token": token, "plex_server": None})
    servers = await find_servers()
    own = [s for s in servers if s["owned"]] or servers
    if len(own) == 1:
        await connect(own[0]["id"])
    return True


async def find_servers() -> List[Dict[str, Any]]:
    """The Plex servers this account can use, with their addresses (this network's first)."""
    token = load_settings().get("plex_token")
    if not token:
        return []
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{PLEX_TV}/api/v2/resources", params={"includeHttps": "1", "includeRelay": "0"},
                        headers=_headers(token))
        r.raise_for_status()
        resources = r.json()
    servers = []
    for res in resources:
        if "server" not in (res.get("provides") or ""):
            continue
        conns = sorted(res.get("connections") or [], key=lambda x: (not x.get("local"), bool(x.get("relay"))))
        uris = []
        for x in conns:
            if x.get("relay") or not x.get("uri"):
                continue
            uris.append(x["uri"])
            # Some routers won't look up *.plex.direct names for home addresses (DNS rebinding
            # protection): the plain address on this network works then
            if x.get("local") and x.get("address") and x.get("port"):
                uris.append(f"http://{x['address']}:{x['port']}")
        servers.append({"id": res.get("clientIdentifier"), "name": res.get("name") or "Plex",
                        "owned": bool(res.get("owned")), "token": res.get("accessToken") or token,
                        "uris": list(dict.fromkeys(uris))})
    return servers


async def connect(server_id: str) -> Dict[str, Any]:
    """Use this server: the first of its addresses that answers is kept."""
    server = next((s for s in await find_servers() if s["id"] == server_id), None)
    if not server:
        raise ValueError("That Plex server isn't on your account")
    async with httpx.AsyncClient(timeout=5, verify=False) as c:
        for uri in server["uris"]:
            try:
                r = await c.get(f"{uri}/identity", headers=_headers(server["token"]))
                if r.status_code == 200:
                    saved = {"id": server["id"], "name": server["name"], "uri": uri, "token": server["token"]}
                    save_settings({"plex_server": saved})
                    print(f"[Plex] Connected to {server['name']} at {uri}")
                    return saved
            except httpx.HTTPError:
                continue
    raise ValueError(f"Couldn't reach {server['name']} from this PC. Is it running?")


def sign_out() -> None:
    save_settings({"plex_token": None, "plex_server": None})


async def libraries(server: Dict[str, Any]) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10, verify=False) as c:
        r = await c.get(f"{server['uri']}/library/sections", headers=_headers(server["token"]))
        r.raise_for_status()
        dirs = (r.json().get("MediaContainer") or {}).get("Directory") or []
    return [{"key": d.get("key"), "title": d.get("title"), "type": d.get("type"),
             "locations": [loc.get("path") for loc in d.get("Location") or [] if loc.get("path")]} for d in dirs]


def _parts(path: str) -> List[str]:
    return [p for p in re.split(r"[\\/]+", path) if p]


def match(libs: List[Dict[str, Any]], folder: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """The library whose folder holds `folder` (as this PC writes it), and `folder` as Plex sees it.
    Matched by the end of the library's path: \\\\NAS\\Plex Videos\\Plex TV\\Show is in the library at
    /volume1/Plex Videos/Plex TV. The longest match wins, TV libraries first."""
    ours = _parts(folder)
    best, best_score = None, (0, False)
    for lib in libs:
        for loc in lib["locations"]:
            theirs = _parts(loc)
            for i in range(1, len(ours) + 1):
                n = 0
                while n < min(i, len(theirs)) and ours[i - 1 - n].lower() == theirs[-1 - n].lower():
                    n += 1
                score = (n, lib["type"] == "show")
                if n and score > best_score:
                    sep = "\\" if "\\" in loc and "/" not in loc else "/"
                    best, best_score = (lib, loc.rstrip("\\/") + "".join(sep + p for p in ours[i:])), score
    return best


async def _refresh(server: Dict[str, Any], library: Dict[str, Any], plex_path: str) -> str:
    """Ask Plex to scan one folder of a library; what happened."""
    async with httpx.AsyncClient(timeout=10, verify=False) as c:
        r = await c.get(f"{server['uri']}/library/sections/{library['key']}/refresh", params={"path": plex_path},
                        headers=_headers(server["token"]))
        if r.status_code == 401:
            return "Plex didn't accept TabloView's sign-in any more: sign in to Plex again (Settings → Plex)"
        r.raise_for_status()
    return f"Asked {server['name']} to scan {plex_path} ({library['title']})"


async def scan(folder: Path) -> str:
    """Ask Plex to scan `folder` (an export's folder); returns what happened, for the log or the page."""
    server = load_settings().get("plex_server")
    if not server:
        return "Not connected to Plex"
    lib = match(await libraries(server), str(folder))
    if not lib:
        return f"{folder} isn't in any of {server['name']}'s libraries"
    return await _refresh(server, *lib)


def _norm(title: Optional[str]) -> str:
    """A show title for comparing: Plex adds the year to some ("Law & Order (1990)"), and punctuation varies."""
    t = re.sub(r"\(\d{4}\)\s*$", "", (title or "").lower().strip()).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"^the\s+", "", t.strip()))


def same_show(ours: Optional[str], theirs: Optional[str]) -> bool:
    """Plex's title for a show is close enough to the Tablo's (one may add a subtitle)."""
    a, b = _norm(ours), _norm(theirs)
    return bool(a and b) and (a == b or a in b or b in a)


def _files(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for m in item.get("Media") or [] for p in m.get("Part") or [] if p.get("file")]


def _same_path(a: str, b: str) -> bool:
    return [p.lower() for p in _parts(a)] == [p.lower() for p in _parts(b)]


def _within(path: str, folder: str) -> bool:
    inner, outer = [p.lower() for p in _parts(path)], [p.lower() for p in _parts(folder)]
    return inner[:len(outer)] == outer


async def _get(c: httpx.AsyncClient, server: Dict[str, Any], path: str, **params) -> Dict[str, Any]:
    r = await c.get(f"{server['uri']}{path}", params=params or None, headers=_headers(server["token"]))
    r.raise_for_status()
    return r.json().get("MediaContainer") or {}


async def find_export(server: Dict[str, Any], library: Dict[str, Any], plex_file: str,
                      since: float) -> Optional[Dict[str, Any]]:
    """The episode Plex made of this file (its path as Plex sees it), once Plex has added it. Found
    among what was added lately, by the file, so it's found under a wrong match too."""
    async with httpx.AsyncClient(timeout=30, verify=False) as c:
        # Plex's filter for "added at or after", with an hour's slack (the NAS's clock may differ)
        items = (await _get(c, server, f"/library/sections/{library['key']}/all", type="4",
                            **{"addedAt>>": str(int(since) - 3600)})).get("Metadata") or []
    return next((i for i in items for p in _files(i) if _same_path(p["file"], plex_file)), None)


async def fix_match(server: Dict[str, Any], item: Dict[str, Any], show: str, plex_show_folder: str) -> Optional[str]:
    """Plex matched the export to another series: match its show to the right one. Only when that
    show in Plex is just this show's folder (re-matching changes every episode in it). What was done."""
    theirs = item.get("grandparentTitle") or ""
    if not show or same_show(show, theirs):
        return None
    key = item.get("grandparentRatingKey")
    async with httpx.AsyncClient(timeout=30, verify=False) as c:
        leaves = (await _get(c, server, f"/library/metadata/{key}/allLeaves")).get("Metadata") or []
        if not all(_within(p["file"], plex_show_folder) for leaf in leaves for p in _files(leaf)):
            return f"Plex matched {show} to {theirs}; left as it is (other files are in that show in Plex)"
        results = (await _get(c, server, f"/library/metadata/{key}/matches", manual="1",
                              title=show)).get("SearchResult") or []
        pick = next((x for x in results if _norm(x.get("name")) == _norm(show)), None)
        if not pick:
            return f"Plex matched {show} to {theirs}, and has no other show called {show} to match it to"
        params = {"guid": pick["guid"], "name": pick.get("name") or show}
        if pick.get("year"):
            params["year"] = str(pick["year"])
        r = await c.put(f"{server['uri']}/library/metadata/{key}/match", params=params,
                        headers=_headers(server["token"]))
        r.raise_for_status()
    year = f" ({params['year']})" if "year" in params else ""
    return f"Plex had matched {show} to {theirs}: matched it to {params['name']}{year} instead"


async def copy_progress(server: Dict[str, Any], item: Dict[str, Any], episode: Dict[str, Any]) -> Optional[str]:
    """Carry the recording's watched status or resume point over to Plex (the MP4 has the same
    timeline). Not when Plex has its own already (the episode was in Plex before)."""
    if item.get("viewCount") or item.get("viewOffset"):
        return None
    params = {"identifier": LIBRARY_ID, "key": item["ratingKey"]}
    pos = int(episode.get("position") or 0)
    async with httpx.AsyncClient(timeout=10, verify=False) as c:
        if episode.get("status") == "Watched":
            r = await c.get(f"{server['uri']}/:/scrobble", params=params, headers=_headers(server["token"]))
            r.raise_for_status()
            return "marked it watched"
        if pos > 30:
            r = await c.get(f"{server['uri']}/:/progress", headers=_headers(server["token"]),
                            params={**params, "time": str(pos * 1000), "state": "stopped"})
            r.raise_for_status()
            return f"set it to resume at {pos // 3600}:{pos // 60 % 60:02d}:{pos % 60:02d}"
    return None


def archived_shows() -> List[str]:
    return list(load_settings().get("plex_archive_shows") or [])


def set_archive(show_id: str, on: bool) -> None:
    save_settings({"plex_archive_shows": [s for s in archived_shows() if s != show_id] + ([show_id] if on else [])})


async def archive(episode_id: str, item: Dict[str, Any], plex_file: str, size: int) -> Optional[str]:
    """For the shows set to: delete the recording from the Tablo, now Plex has the whole export."""
    ep = get_episode_by_id(episode_id)
    if not ep or ep.get("show_id") not in archived_shows():
        return None
    if ep.get("protected"):
        return "kept it on the Tablo (it's protected)"
    if ep.get("recording_state") != "finished" or ep.get("incomplete"):
        return "kept it on the Tablo (the recording isn't complete)"
    part = next((p for p in _files(item) if _same_path(p["file"], plex_file)), {})
    if part.get("size") and int(part["size"]) != size:
        return "kept it on the Tablo (Plex's copy isn't the same size as the export)"
    from .tablo_client import tablo_manager
    if not tablo_manager.is_authenticated:
        return "couldn't delete it from the Tablo (not connected)"
    if not await tablo_manager.delete_airing(ep["path"]):
        return "couldn't delete it from the Tablo (the Tablo refused)"
    delete_episode(ep["id"])
    return "deleted it from the Tablo"


async def after_export(output_path: Path, episode: Optional[Dict[str, Any]] = None) -> None:
    """After an export finished: have Plex scan its folder, wait for Plex to add it, then fix its
    match, carry the watched status over, and delete it from the Tablo if its show is set to. Never
    fails the export: what happens goes in the log."""
    s = load_settings()
    server = s.get("plex_server")
    if not server:
        return
    since = time.time()
    name = output_path.name
    try:
        libs = await libraries(server)
        m = match(libs, str(output_path.parent))
        if not m:
            print(f"[Plex] {output_path.parent} isn't in any of {server['name']}'s libraries")
            return
        library, plex_folder = m
        if s.get("plex_scan", True):
            print(f"[Plex] {await _refresh(server, library, plex_folder)}")
        if not episode:
            return
        sep = "/" if "/" in plex_folder else "\\"
        plex_file = plex_folder.rstrip("\\/") + sep + name
        item = None
        for _ in range(FIND_WAIT // FIND_EVERY):
            await asyncio.sleep(FIND_EVERY)
            try:
                item = await find_export(server, library, plex_file, since)
            except httpx.HTTPError:
                item = None
            if item:
                break
        if not item:
            print(f"[Plex] {name} didn't show up in Plex within {FIND_WAIT // 60} minutes; nothing more done with it")
            return
        _show_cache.clear()  # the show pages' In Plex tags
        done = []
        if s.get("plex_fix_match", True) and s.get("export_show_folders"):
            # The show's own folder: Show\Season 01\file, or Show\file without a season
            folder = output_path.parent
            show_folder = folder.parent if re.fullmatch(r"Season \d+", folder.name) else folder
            sm = match(libs, str(show_folder))
            fixed = await fix_match(server, item, episode.get("show_title") or "", sm[1]) if sm else None
            if fixed:
                print(f"[Plex] {fixed}")
                await asyncio.sleep(20)  # Plex fetches the right show's details
                item = await find_export(server, library, plex_file, since) or item
        if s.get("plex_copy_watched", True):
            copied = await copy_progress(server, item, get_episode_by_id(episode["id"]) or episode)
            if copied:
                done.append(copied)
        archived = await archive(episode["id"], item, plex_file, output_path.stat().st_size)
        if archived:
            done.append(archived)
        print(f"[Plex] {name} is in Plex{': ' + ', '.join(done) if done else ''}")
    except Exception as e:
        print(f"[Plex] After exporting {name}: {e}")


async def _show_episodes(server: Dict[str, Any], title: str) -> List[Dict[str, Any]]:
    """Plex's episodes of the show with this title, in any of its TV libraries (kept a few minutes)."""
    cache_key = (server["uri"], _norm(title))
    hit = _show_cache.get(cache_key)
    if hit and time.time() - hit[0] < SHOW_CACHE_TTL:
        return hit[1]
    episodes: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20, verify=False) as c:
        for lib in await libraries(server):
            if lib["type"] != "show":
                continue
            shows = (await _get(c, server, f"/library/sections/{lib['key']}/all", type="2",
                                title=title)).get("Metadata") or []
            for sh in shows:
                if _norm(sh.get("title")) == _norm(title):
                    episodes += (await _get(c, server, f"/library/metadata/{sh['ratingKey']}/allLeaves")).get("Metadata") or []
    _show_cache[cache_key] = (time.time(), episodes)
    return episodes


def have(episodes: List[Dict[str, Any]], theirs: List[Dict[str, Any]]) -> List[str]:
    """Which recordings (of one show) are among Plex's episodes `theirs`: by the export's file name,
    the season and episode, or without those, the original air date."""
    from .transcode import transcode_manager
    names = {_parts(p["file"])[-1].lower() for i in theirs for p in _files(i)}
    numbers = {(int(i.get("parentIndex") or 0), int(i.get("index") or 0)) for i in theirs}
    aired = {str(i.get("originallyAvailableAt") or "")[:10] for i in theirs} - {""}
    out = []
    for ep in episodes:
        f = transcode_manager._episode_facts(ep)
        numbered = f["season"] > 0 and f["episode"] > 0
        if (transcode_manager.export_name(ep)[0].lower() in names
                or (numbered and (f["season"], f["episode"]) in numbers)
                or (not numbered and f["aired"] in aired)):
            out.append(ep["id"])
    return out


async def in_plex(episodes: List[Dict[str, Any]]) -> List[str]:
    """Which of these recordings (all of one show) Plex has already."""
    server = load_settings().get("plex_server")
    if not server or not episodes:
        return []
    return have(episodes, await _show_episodes(server, episodes[0].get("show_title") or ""))


async def status() -> Dict[str, Any]:
    """For Settings → Plex: signed in or not, the server, and the library exports go into."""
    s = load_settings()
    out: Dict[str, Any] = {"signed_in": bool(s.get("plex_token")), "scan": s.get("plex_scan", True),
                           "fix_match": s.get("plex_fix_match", True), "copy_watched": s.get("plex_copy_watched", True),
                           "show_folders": bool(s.get("export_show_folders")), "archive_shows": len(archived_shows()),
                           "export_folder": str(exports_dir()), "server": None}
    server = s.get("plex_server")
    if not out["signed_in"]:
        return out
    if not server:
        try:
            out["servers"] = [{"id": x["id"], "name": x["name"], "owned": x["owned"]} for x in await find_servers()]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                sign_out()
                return {**out, "signed_in": False}
            out["error"] = f"Couldn't get your Plex servers: {e}"
        except httpx.HTTPError as e:
            out["error"] = f"Couldn't reach plex.tv: {e}"
        return out
    out["server"] = {"name": server["name"], "uri": server["uri"]}
    try:
        libs = await libraries(server)
        out["libraries"] = [{"title": x["title"], "type": x["type"]} for x in libs]
        m = match(libs, str(exports_dir()))
        out["export_library"] = {"title": m[0]["title"], "path": m[1]} if m else None
    except httpx.HTTPStatusError as e:
        out["error"] = ("Plex didn't accept TabloView's sign-in any more: sign out and in again"
                        if e.response.status_code == 401 else f"Plex answered {e.response.status_code}")
    except httpx.HTTPError:
        out["error"] = f"Couldn't reach {server['name']} at {server['uri']}. Is it running?"
    return out
