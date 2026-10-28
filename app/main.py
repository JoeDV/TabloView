"""Main FastAPI application for TabloView."""

import asyncio
import socket
import ipaddress
from pathlib import Path
from contextlib import asynccontextmanager

import httpx

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response, JSONResponse, RedirectResponse

from .config import (
    APP_NAME, APP_VERSION, BASE_DIR, RESOURCE_DIR, STATIC_DIR, TRANSCODE_DIR, DOWNLOADS_DIR, IMAGE_CACHE_DIR, HOST, PORT,
)
from . import autoexport, commercials, dropouts, encoders, export_pace, lanauth, netcheck, redact, streaming, whatsnew
from .settings import exports_dir
from .database import get_export_jobs, fail_interrupted_exports
from .database import init_db
from .tablo_client import tablo_manager
from .sync_service import sync_service, auto_sync_loop
from .transcode import transcode_manager

from .routes import auth, shows, episodes, system, debug, guide, live, watchlist
from .routes import streaming as streaming_routes
from .routes import devtools
from .routes import plex_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sign-in tokens and the account's email never reach the log (it gets pasted into forum posts)
    redact.install()
    asyncio.create_task(asyncio.to_thread(netcheck.tailscale))  # this PC's Tailscale name, for _on_tailnet
    # Startup: initialize database tables
    print("[Startup] Initializing Tablo SQLite database...")
    init_db()
    whatsnew.init()
    # Find out once which graphics-chip video encoder works here, before the first playback
    encoders.detect_in_background()

    # If credentials/device already loaded, kick off an initial library sync in background
    # (sync_library starts the guide sync itself once it finishes)
    if tablo_manager.is_authenticated:
        print(f"[Startup] Found cached Tablo device: {tablo_manager.device.name} ({tablo_manager.device.local_url})")
        # The Tablo may have a new address since sign-in (a router's choice): the account knows
        asyncio.create_task(tablo_manager.refresh_address())
        asyncio.create_task(sync_service.sync_library())
    else:
        print("[Startup] No authenticated Tablo device yet. Ready for login via web UI.")

    # Exports cut off by TabloView closing: mark them, and remove their unfinished file
    for job in fail_interrupted_exports():
        print(f"[Startup] Export interrupted when TabloView closed: {job.get('filename')}")
        if job.get("filepath"):
            p = Path(job["filepath"])
            p.with_name(p.stem + ".part.ts").unlink(missing_ok=True)

    auto_sync = asyncio.create_task(auto_sync_loop(sync_service))
    ad_finder = asyncio.create_task(commercials.worker_loop())
    auto_exports = asyncio.create_task(autoexport.worker_loop())
    dropout_finder = asyncio.create_task(dropouts.worker_loop())
    streaming_guide = asyncio.create_task(streaming.worker_loop())
    unused_streams = asyncio.create_task(transcode_manager.abandoned_loop())

    yield

    auto_sync.cancel()
    ad_finder.cancel()
    auto_exports.cancel()
    dropout_finder.cancel()
    streaming_guide.cancel()
    unused_streams.cancel()
    # Shutdown: clean up transcode sessions
    print("[Shutdown] Cleaning up stream sessions...")
    for sid in list(transcode_manager.sessions.keys()):
        transcode_manager.stop_session(sid)


app = FastAPI(
    title=APP_NAME,
    description="Recordings, guide and live TV for the Tablo 4th Gen DVR",
    version=APP_VERSION,
    lifespan=lifespan
)


class TextGZip:
    """Compress the page, scripts and data (the Live TV guide is ~600 KB of JSON, about a tenth of that
    compressed: it matters over Wi-Fi to other devices), but not video, images or downloads, which are
    compressed already and would only cost CPU."""
    SKIP = ("/api/transcoded/", "/api/hls/", "/api/export-relay/", "/api/images/", "/downloads/")

    def __init__(self, app):
        from starlette.middleware.gzip import GZipMiddleware
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith(self.SKIP)                 and not scope["path"].endswith((".ts", ".m3u8", ".jpg", ".png")):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


app.add_middleware(TextGZip)

# No CORS middleware: the UI is served from this same origin, and allowing any
# origin would let arbitrary websites drive the API (e.g. delete recordings).


@app.exception_handler(httpx.TransportError)
async def tablo_not_answering(request: Request, exc: httpx.TransportError):
    """Any request that failed because the Tablo didn't answer gets the same plain explanation."""
    return JSONResponse(status_code=503, content={"detail": tablo_manager.UNREACHABLE_MESSAGE})

_PC_NAME = socket.gethostname().lower()
_LOCAL_NAMES = {"localhost", _PC_NAME, f"{_PC_NAME}.local"}
# Tailscale's full name for this PC ("hplaptop.tailc0c2e.ts.net"), for a phone or laptop away from
# home on the owner's tailnet. Only names under ts.net, which Tailscale's DNS answers, so a
# DNS-rebinding page can't point one at this PC; and only this PC's own (Tailscale's name for it can
# differ from the PC's, e.g. "hplaptop-1": asked of Tailscale, at most every 5 minutes)
def _tailscale_name() -> str:
    return (netcheck.tailscale_now() or {}).get("name") or ""


def _on_tailnet(host: str) -> bool:
    labels = host.split(".")
    if len(labels) != 4 or not host.endswith(".ts.net"):
        return False
    return labels[0] == _PC_NAME or host == _tailscale_name()


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_OTHER_SITES = {"cross-site", "same-site"}  # same-site: another program's page on this PC (another port)


def _host_allowed(host_header: str) -> bool:
    """Accept localhost, this PC's name (also its Tailscale name), or a literal IP. Rejects other DNS
    names, which is what a DNS-rebinding page would use to reach this server from the user's browser."""
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    else:
        host = host.rsplit(":", 1)[0]
    if host in _LOCAL_NAMES or _on_tailnet(host):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


@app.middleware("http")
async def request_guard(request: Request, call_next):
    export_pace.note_port(request.scope.get("server"))  # exports fetch through TabloView's own port
    if not _host_allowed(request.headers.get("host", "")):
        return JSONResponse({"detail": "Host not allowed"}, status_code=403)
    # State-changing calls must carry a custom header. Browsers won't let another website add it
    # without a CORS preflight, which this server never approves.
    if request.method in _UNSAFE_METHODS and request.headers.get("x-tabloview") != "1":
        return JSONResponse({"detail": "Missing X-TabloView header"}, status_code=403)
    # Some reads use a tuner (the VLC links), so other websites can't make them either: browsers mark
    # requests a page on another site makes. TabloView's own pages are same-origin; VLC, calendar apps
    # and typed addresses send no such mark (or "none")
    if request.headers.get("sec-fetch-site") in _OTHER_SITES and \
            (request.url.path.startswith("/api/") or request.url.path.startswith("/downloads/")):
        return JSONResponse({"detail": "Requests from other websites aren't allowed"}, status_code=403)
    # Other devices on the network need the PIN (this PC never does)
    client = lanauth.client_address(request)
    path = request.url.path
    why = lanauth.blocked(path, client, request.cookies.get(lanauth.COOKIE), request.headers)
    if why == "lan_off":
        message = ("Network access is off on the PC running TabloView. To use it from this device, turn on "
                   "Allow other devices on my network there, under Settings → Desktop & network.")
        if path.startswith("/api/") or path.startswith("/downloads/"):
            return JSONResponse({"detail": message, "code": why}, status_code=403)
        return HTMLResponse(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                            f"<title>TabloView</title><body style='font:18px system-ui;margin:2em;background:#0b0d12;color:#f2f4f8'>"
                            f"<h2>TabloView</h2><p>{message}</p>", status_code=403)
    if why:
        message = ("Enter the PIN to use TabloView on this device." if why == "pin_required" else
                   "Set a PIN on the PC running TabloView (Settings page) to use it from other devices.")
        return JSONResponse({"detail": message, "code": why}, status_code=401)
    # A signed-in device: noted for the Settings page's list of devices using TabloView
    if path.startswith("/api/") and path not in lanauth.PUBLIC_PATHS and not lanauth.from_this_pc(request):
        lanauth.note_seen(client, request.headers.get("user-agent"))
    return await call_next(request)


def safe_join(base: Path, *parts: str) -> Path:
    """Join user-supplied path parts onto base, rejecting anything that escapes it."""
    candidate = base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise HTTPException(status_code=404, detail="File not found")
    return candidate

# Include API Routers
app.include_router(auth.router)
app.include_router(shows.router)
app.include_router(episodes.router)
app.include_router(guide.router)
app.include_router(live.router)
app.include_router(system.router)
app.include_router(debug.router)
app.include_router(watchlist.router)
if devtools.ENABLED:  # developer tools (TABLOVIEW_DEV_TOOLS=1): never in the app people use
    app.include_router(devtools.router)
app.include_router(streaming_routes.router)
app.include_router(plex_routes.router)


# ---------------------------------------------------------------------------
# Tablo Local Image Proxy
# ---------------------------------------------------------------------------

@app.get("/api/images/{image_id}")
async def get_tablo_image(image_id: str):
    """Proxy cover and poster images directly from Tablo 4th Gen hardware with local disk caching."""
    if not image_id.isalnum():
        raise HTTPException(status_code=404, detail="Image not found")
    cached_path = IMAGE_CACHE_DIR / f"{image_id}.jpg"
    if cached_path.exists() and cached_path.stat().st_size > 0:
        return FileResponse(
            cached_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"}
        )

    placeholder_file = STATIC_DIR / "placeholder.svg"
    placeholder_bytes = placeholder_file.read_bytes() if placeholder_file.exists() else b""

    if not tablo_manager.device:
        return Response(content=placeholder_bytes, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})

    url = f"{tablo_manager.device.local_url.rstrip('/')}/images/{image_id}"
    try:
        resp = await tablo_manager._http.get(url, timeout=12, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 0:
            # Save to disk cache for instant future loads
            try:
                cached_path.write_bytes(resp.content)
            except Exception:
                pass
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=604800"}
            )
    except Exception as e:
        print(f"[ImageProxy] Error fetching image {image_id}: {e}")

    # If Tablo hardware returns 404 or temporary error, return the clean SVG placeholder
    # But DO NOT cache it for 24 hours so any transient error can recover
    return Response(
        content=placeholder_bytes,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )



# ---------------------------------------------------------------------------
# HLS Direct Proxy & Transcoded Streaming Routes
# ---------------------------------------------------------------------------

@app.get("/api/export-relay/{relay_id}/{name}")
async def export_relay(relay_id: str, name: str):
    """An export's recording, handed to its FFmpeg at the pace that suits the moment (app/export_pace.py)."""
    return await export_pace.serve(relay_id, name)


@app.get("/api/hls/{session_id}/{subpath:path}")
async def proxy_hls_stream(session_id: str, subpath: str, request: Request):
    """Proxy HLS segments and manifests with URL rewriting."""
    query_str = str(request.url.query)
    return await transcode_manager.proxy_hls_request(session_id, subpath, query_str, request.headers.get("range"))


@app.get("/api/transcoded/{session_id}/{filename:path}")
async def serve_transcoded_file(session_id: str, filename: str):
    """Serve transcoded HLS playlist and video segments."""
    file_path = safe_join(TRANSCODE_DIR, session_id, filename)
    transcode_manager.touch(session_id)
    if not file_path.exists():
        # Wait briefly for manifest if just starting
        if filename.endswith(".m3u8"):
            for _ in range(15):
                if file_path.exists():
                    break
                await asyncio.sleep(0.3)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Transcoded segment not ready or not found")

    if filename.endswith(".m3u8"):
        # FFmpeg replaces the playlist by renaming a new copy over it; read at that instant, Windows
        # refuses for a moment (PermissionError). Try again rather than fail the player's request.
        for attempt in range(6):
            try:
                content = file_path.read_bytes()
                break
            except PermissionError:
                if attempt == 5:
                    raise HTTPException(status_code=503, detail="Playlist busy, try again")
                await asyncio.sleep(0.05)
        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache, no-store",
                "Content-Disposition": "inline"
            }
        )

    return FileResponse(
        str(file_path),
        # No Access-Control-Allow-Origin: TabloView's pages are on this same address, and VLC doesn't
        # ask; allowing any origin only let other websites read the video
        media_type="video/mp2t" if filename.endswith(".ts") else "image/jpeg" if filename.endswith(".jpg") else "application/octet-stream",
    )


@app.get("/downloads/{filename:path}")
async def serve_downloaded_mp4(filename: str):
    """Serve completed MP4 exports for download or browser playback. Exports made before the export
    folder was changed are found through their export job."""
    file_path = safe_join(exports_dir(), filename)
    if not file_path.is_file():
        job = next((j for j in get_export_jobs() if j.get("filename") == filename and j.get("status") == "completed"), None)
        file_path = Path(job["filepath"]) if job and job.get("filepath") else file_path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        filename=filename
    )


# ---------------------------------------------------------------------------
# Static Frontend Serving
# ---------------------------------------------------------------------------

# Mount static folder (inside the install folder when packaged)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return Response(content=f"{APP_NAME} is starting up...", media_type="text/plain")
    return FileResponse(
        str(index_file),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/tv")
async def serve_tv():
    """TabloView for a TV's browser: a few big screens for a remote (static/tv.js)."""
    return FileResponse(str(STATIC_DIR / "tv.html"), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# The TabloView app for Google TV and Fire TV (tvapp/). On the TV, Downloader fetches it from this PC's
# address shown on the Settings page plus /app, much less to type with a remote than GitHub's link.
# The installer carries it; a copy without it (Mac, Linux, from source) sends people to GitHub's
TV_APP_LATEST = "https://github.com/JoeDV/TabloView/releases/latest/download/TabloView-TV.apk"


@app.get("/app")
async def tv_app():
    for apk in (RESOURCE_DIR / "tvapp" / "TabloView-TV.apk", BASE_DIR / "dist" / "TabloView-TV.apk"):
        if apk.is_file():
            return FileResponse(str(apk), media_type="application/vnd.android.package-archive", filename="TabloView-TV.apk")
    return RedirectResponse(TV_APP_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
