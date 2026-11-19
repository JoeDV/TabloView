"""The Tablo as a network tuner for Plex, Jellyfin, Emby and Channels DVR (a cord-cutter request,
2026-11-18). The 4th Gen Tablo can't be added to them directly; TabloView answers as an HDHomeRun
would, on a port of its own (TUNER_PORT), and hands each channel over as the Tablo sends it.

  /discover.json, /lineup.json, /lineup_status.json, /device.xml   what HDHomeRun clients read
  /auto/v<number>       the channel (6.1...) as a plain MPEG-TS stream, copied: no converting
  /xmltv.xml            the guide, from the Tablo's own listings (about 12 days)
  /lineup.m3u           the channels as a playlist (Channels DVR's M3U source, TiviMate...)

Off unless turned on (settings "tuner_enabled"). It answers only this PC and the home network:
those apps can't type TabloView's PIN, and a real HDHomeRun asks for nothing either. Each stream
uses one of the Tablo's tuners, like live TV in TabloView, and the Tablo is told when it ends.
"""

import asyncio
import contextlib
import json
import os
import secrets
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from xml.sax.saxutils import escape, quoteattr

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from . import background, childproc
from .config import APP_VERSION, FFMPEG_PATH
from .netcheck import away_from_home
from .settings import load_settings, save_settings

TUNER_PORT = 5004  # an HDHomeRun's own stream port
LINEUP_SECONDS = 600  # the channel list, kept 10 minutes
GUIDE_SECONDS = 1800  # the guide, kept half an hour
GUIDE_DAYS = 14
NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_cache: Dict[str, Any] = {"lineup": None, "lineup_at": 0.0, "guide": None, "guide_at": 0.0}
streams: Dict[int, Dict[str, Any]] = {}  # what's being sent now, for Settings
_server: Dict[str, Any] = {"server": None, "task": None, "error": None}


def device_id() -> str:
    """This TabloView's HDHomeRun ID (8 hex digits), made once and kept, so the apps know it again."""
    s = load_settings()
    if not s.get("tuner_device_id"):
        save_settings({"tuner_device_id": secrets.token_hex(4).upper()})
        s = load_settings()
    return s["tuner_device_id"]


@app.middleware("http")
async def home_network_only(request: Request, call_next):
    if away_from_home(request.client.host if request.client else None):
        return PlainTextResponse("TabloView's tuner answers only this PC and your home network.", status_code=403)
    return await call_next(request)


def base_url(request: Request) -> str:
    return f"http://{request.headers.get('host') or f'{request.url.hostname}:{TUNER_PORT}'}"


async def lineup() -> List[Dict[str, Any]]:
    """The Tablo's antenna channels: guide number, name, logo, identifier. Kept LINEUP_SECONDS."""
    if _cache["lineup"] is not None and time.time() - _cache["lineup_at"] < LINEUP_SECONDS:
        return _cache["lineup"]
    from .routes.live import get_live_epg
    from .tablo_client import tablo_manager
    if not tablo_manager.is_authenticated:
        return []
    epg = await get_live_epg(hours=1, start_iso=None, kind="ota")
    chans = [{"number": f"{c['major']}.{c['minor']}", "name": c.get("name") or c.get("call_sign") or "",
              "call_sign": c.get("call_sign") or "", "network": c.get("network") or "",
              "logo": c.get("logo_url") if str(c.get("logo_url") or "").startswith("http") else None,
              "id": c["channel_id"], "hd": str(c.get("resolution") or "").startswith(("720", "1080"))}
             for c in epg.get("channels") or [] if c.get("kind") == "ota" and c.get("major")]
    _cache.update(lineup=chans, lineup_at=time.time())
    return chans


async def tuner_count() -> int:
    from .routes.live import model_tuner_count
    try:
        return await model_tuner_count() or 2
    except Exception:
        return 2


@app.get("/discover.json")
async def discover(request: Request):
    base = base_url(request)
    return {"FriendlyName": "TabloView", "Manufacturer": "TabloView", "ModelNumber": "HDTC-2US",
            "FirmwareName": "hdhomeruntc_atsc", "FirmwareVersion": APP_VERSION, "DeviceID": device_id(),
            "DeviceAuth": "tabloview", "BaseURL": base, "LineupURL": f"{base}/lineup.json",
            "TunerCount": await tuner_count()}


@app.get("/lineup_status.json")
async def lineup_status():
    return {"ScanInProgress": 0, "ScanPossible": 0, "Source": "Antenna", "SourceList": ["Antenna"]}


@app.post("/lineup.post")
async def lineup_post():
    return Response(status_code=200)  # (a channel scan is done on the Tablo, from Tablo's own app)


@app.get("/lineup.json")
async def lineup_json(request: Request):
    base = base_url(request)
    return [{"GuideNumber": c["number"], "GuideName": c["name"], "URL": f"{base}/auto/v{c['number']}",
             **({"HD": 1} if c["hd"] else {})} for c in await lineup()]


@app.get("/device.xml")
async def device_xml(request: Request):
    base = base_url(request)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <URLBase>{escape(base)}</URLBase>
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
    <friendlyName>TabloView</friendlyName>
    <manufacturer>TabloView</manufacturer>
    <modelName>HDTC-2US</modelName>
    <modelNumber>HDTC-2US</modelNumber>
    <serialNumber>{device_id()}</serialNumber>
    <UDN>uuid:{device_id().lower()}-0000-0000-0000-000000000000</UDN>
  </device>
</root>
"""
    return Response(xml, media_type="application/xml")


@app.get("/lineup.m3u")
async def lineup_m3u(request: Request):
    base = base_url(request)
    lines = [f'#EXTM3U url-tvg="{base}/xmltv.xml"']
    attr = lambda v: '"' + str(v).replace('"', "'") + '"'  # (M3U isn't XML: & stays &)
    for c in await lineup():
        logo = f" tvg-logo={attr(c['logo'])}" if c["logo"] else ""
        lines += [f'#EXTINF:-1 tvg-id="{c["number"]}" tvg-chno="{c["number"]}" tvg-name={attr(c["name"])}'
                  f'{logo} group-title="Tablo",{c["number"]} {c["name"]}', f"{base}/auto/v{c['number']}"]
    return PlainTextResponse("\n".join(lines) + "\n", media_type="audio/x-mpegurl")


def _xmltv_time(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def guide_xml(chans: List[Dict[str, Any]], airings: List[Dict[str, Any]], base: str = "") -> str:
    """XMLTV: a channel per lineup entry (its id is the guide number, as in lineup.json and the M3U)
    and the airings on them, each with its show's poster (from the Tablo, through /images)."""
    by_id = {c["id"]: c for c in chans}
    by_call = {c["call_sign"].upper(): c for c in chans if c["call_sign"]}
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="TabloView">']
    for c in chans:
        out.append(f'  <channel id="{escape(c["number"])}">')
        # The plain name first: Plex shows the number before the first one ("6.1 6.1 WRTV" otherwise)
        for name in dict.fromkeys([c["name"], f'{c["number"]} {c["name"]}', c["call_sign"], c["number"]]):
            if name:
                out.append(f"    <display-name>{escape(name)}</display-name>")
        if c["logo"]:
            out.append(f"    <icon src={quoteattr(c['logo'])}/>")
        out.append("  </channel>")
    for a in airings:
        c = by_id.get(a.get("channel_identifier")) or by_call.get((a.get("channel_call_sign") or "").upper())
        if not c or not a.get("air_datetime") or not a.get("duration"):
            continue
        start = datetime.fromisoformat(a["air_datetime"].replace("Z", "+00:00"))
        stop = start + timedelta(seconds=int(a["duration"]))
        out.append(f'  <programme start="{_xmltv_time(a["air_datetime"])}" '
                   f'stop="{stop.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")}" channel="{escape(c["number"])}">')
        out.append(f"    <title>{escape(a.get('show_title') or '')}</title>")
        if a.get("episode_title"):
            out.append(f"    <sub-title>{escape(a['episode_title'])}</sub-title>")
        if a.get("description"):
            out.append(f"    <desc>{escape(a['description'])}</desc>")
        for g in a.get("genres") or []:
            out.append(f"    <category>{escape(str(g))}</category>")
        image = str(a.get("cover_url") or "").rsplit("/", 1)[-1]
        if base and image.isalnum():
            out.append(f'    <icon src="{escape(base)}/images/{image}"/>')
        s, e = int(a.get("season_number") or 0), int(a.get("episode_number") or 0)
        if e:
            out.append(f'    <episode-num system="xmltv_ns">{max(s - 1, 0) if s else ""}.{e - 1}.</episode-num>')
            out.append(f'    <episode-num system="onscreen">{f"S{s:02d}" if s else ""}E{e:02d}</episode-num>')
        out.append("    <new/>" if a.get("is_new") else "    <previously-shown/>")
        if a.get("is_premiere"):
            out.append("    <premiere/>")
        out.append("  </programme>")
    out.append("</tv>")
    return "\n".join(out) + "\n"


def guide_airings(days: int = GUIDE_DAYS) -> List[Dict[str, Any]]:
    """The Tablo's antenna listings from now on, with each show's description and genres."""
    from .database import get_connection
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT ga.show_title, ga.episode_title, ga.season_number, ga.episode_number, ga.air_datetime,
                   ga.duration, ga.channel_call_sign, ga.channel_identifier, ga.is_new, ga.is_premiere,
                   g.description, g.genres, g.cover_url
            FROM guide_airings ga LEFT JOIN guide_shows g ON g.path = ga.series_path
            WHERE datetime(ga.air_datetime, '+' || ga.duration || ' seconds') > datetime(?)
              AND datetime(ga.air_datetime) < datetime(?)
            ORDER BY ga.channel_identifier, ga.air_datetime
        """, (now.strftime("%Y-%m-%dT%H:%M:%SZ"), (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchall()
    found = []
    for r in rows:
        a = dict(r)
        try:
            a["genres"] = json.loads(a["genres"]) if a["genres"] else []
        except ValueError:
            a["genres"] = []
        found.append(a)
    return found


@app.get("/xmltv.xml")
async def xmltv(request: Request):
    base = base_url(request)
    if _cache["guide"] is None or _cache.get("guide_base") != base or time.time() - _cache["guide_at"] >= GUIDE_SECONDS:
        chans = await lineup()
        _cache.update(guide=guide_xml(chans, await asyncio.to_thread(guide_airings), base), guide_at=time.time(),
                      guide_base=base)
    return Response(_cache["guide"], media_type="application/xml")


@app.get("/images/{image_id}")
async def image(image_id: str):
    """A show's poster for the guide: the Tablo's, as TabloView shows it (and keeps it)."""
    from .main import get_tablo_image
    return await get_tablo_image(image_id)


def stream_cmd(playlist_url: str) -> List[str]:
    """The channel as the Tablo sends it, picture and every sound track, re-wrapped as MPEG-TS for
    the app reading it: nothing converted (captions stay in the picture)."""
    return [FFMPEG_PATH, "-hide_banner", "-loglevel", "error", "-fflags", "+discardcorrupt",
            "-i", playlist_url, "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-f", "mpegts", "pipe:1"]


@app.get("/auto/v{number}")
async def channel_stream(number: str, request: Request):
    from tablo_api import TabloClient
    from .routes.live import all_tuners_busy_message
    from .tablo_client import tablo_manager
    from .transcode import transcode_manager
    c = next((c for c in await lineup() if c["number"] == number), None)
    if not c:
        raise HTTPException(status_code=404, detail="No such channel")
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=503, detail="TabloView isn't signed in to a Tablo")
    await transcode_manager.wait_for_ended_sessions()
    try:
        watch = await asyncio.to_thread(TabloClient(tablo_manager.device).watch, c["id"])
        if not watch or not watch.playlist_url:
            raise ValueError("no playlist")
    except Exception as e:
        print(f"[Tuner] Couldn't tune {number} for {request.client.host if request.client else '?'}: {e}")
        busy = await all_tuners_busy_message()
        raise HTTPException(status_code=503, detail=busy or "The Tablo couldn't tune that channel")
    proc = subprocess.Popen(stream_cmd(watch.playlist_url), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=NO_WINDOW, **childproc.popen_kwargs())
    childproc.tie_to_app(proc)
    who = request.client.host if request.client else "?"
    streams[proc.pid] = {"channel": f"{number} {c['name']}", "client": who, "since": time.time()}
    print(f"[Tuner] {number} {c['name']} to {who}")

    async def body():
        try:
            while True:
                chunk = await asyncio.to_thread(proc.stdout.read, 188 * 512)
                if not chunk:
                    break
                yield chunk
        finally:
            with contextlib.suppress(Exception):
                proc.kill()
                proc.wait(timeout=5)
            streams.pop(proc.pid, None)
            background.start(tablo_manager.end_watch_session(watch.token))  # the tuner back straight away
            print(f"[Tuner] {number} {c['name']} to {who} ended")

    return StreamingResponse(body(), media_type="video/mp2t")


# --- Running it: a second, small web server beside TabloView's own, while turned on ---

def _make_server(port: int):
    import uvicorn

    class TunerServer(uvicorn.Server):
        @contextlib.contextmanager
        def capture_signals(self):  # TabloView's own server handles Ctrl+C and closing
            yield

    # (TABLOVIEW_TUNER_HOST=127.0.0.1 for testing: no Windows firewall question for a developer copy)
    host = os.getenv("TABLOVIEW_TUNER_HOST") or "0.0.0.0"
    return TunerServer(uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False))


async def start() -> None:
    """Start answering, if turned on and not already (at startup, and when turned on in Settings)."""
    if not load_settings().get("tuner_enabled") or (_server["task"] and not _server["task"].done()):
        return
    port = int(load_settings().get("tuner_port") or TUNER_PORT)
    server = _make_server(port)
    _server.update(server=server, error=None, port=port)

    async def run():
        try:
            await server.serve()
        except (SystemExit, Exception) as e:  # (uvicorn exits when the port is taken)
            _server["error"] = f"Port {port} is in use by another program" if isinstance(e, SystemExit) else str(e)
        if not server.started and not _server["error"]:
            _server["error"] = f"Port {port} is in use by another program"
        if _server["error"]:
            print(f"[Tuner] Couldn't start: {_server['error']}")
    _server["task"] = asyncio.create_task(run())
    await asyncio.sleep(0.5)
    if server.started:
        print(f"[Tuner] Answering as an HDHomeRun on port {port}")


async def stop() -> None:
    server, task = _server.get("server"), _server.get("task")
    if server:
        server.should_exit = True
    if task:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, 10)
    _server.update(server=None, task=None)


def status() -> Dict[str, Any]:
    server = _server.get("server")
    return {"enabled": bool(load_settings().get("tuner_enabled")), "running": bool(server and server.started),
            "port": _server.get("port") or int(load_settings().get("tuner_port") or TUNER_PORT),
            "error": _server.get("error"), "streams": list(streams.values())}
