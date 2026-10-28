"""Plex: after an export, ask your Plex server to scan the folder it went into, so the episode shows up
in Plex right away. Plex usually doesn't notice new files on a network share by itself, so exports
otherwise wait for its next scheduled scan.

Sign-in is Plex's own: TabloView asks plex.tv for a PIN, you approve it on app.plex.tv, and TabloView
gets a token for your account (kept in settings.json, never shown or logged). The server's address and
its own token come from plex.tv's list of your servers; the first address that answers is kept.

Plex sees its library folders from where it runs (/volume1/Plex Videos/Plex TV on a NAS) while
TabloView writes through the network (\\\\NAS\\Plex Videos\\Plex TV), so an export is matched to a
library by the end of the paths, and the scan is asked for in Plex's own terms.
"""

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from .config import APP_VERSION
from .settings import exports_dir, load_settings, save_settings

PLEX_TV = "https://plex.tv"
PRODUCT = "TabloView"


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


async def scan(folder: Path) -> str:
    """Ask Plex to scan `folder` (an export's folder); returns what happened, for the log or the page."""
    server = load_settings().get("plex_server")
    if not server:
        return "Not connected to Plex"
    lib = match(await libraries(server), str(folder))
    if not lib:
        return f"{folder} isn't in any of {server['name']}'s libraries"
    library, plex_path = lib
    async with httpx.AsyncClient(timeout=10, verify=False) as c:
        r = await c.get(f"{server['uri']}/library/sections/{library['key']}/refresh", params={"path": plex_path},
                        headers=_headers(server["token"]))
        if r.status_code == 401:
            return "Plex didn't accept TabloView's sign-in any more: sign in to Plex again (Device → Plex)"
        r.raise_for_status()
    return f"Asked {server['name']} to scan {plex_path} ({library['title']})"


async def scan_after_export(output_path: Path) -> None:
    """After an export finished: scan its folder in Plex, if that's turned on. Never fails the export."""
    s = load_settings()
    if not (s.get("plex_server") and s.get("plex_scan", True)):
        return
    try:
        print(f"[Plex] {await scan(output_path.parent)}")
    except Exception as e:
        print(f"[Plex] Couldn't ask Plex to scan the new export: {e}")


async def status() -> Dict[str, Any]:
    """For Device → Plex: signed in or not, the server, and the library exports go into."""
    s = load_settings()
    out: Dict[str, Any] = {"signed_in": bool(s.get("plex_token")), "scan": s.get("plex_scan", True),
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
