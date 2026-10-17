"""Main FastAPI application for Tablo Classic UI."""

import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from .config import BASE_DIR, TRANSCODE_DIR, DOWNLOADS_DIR, IMAGE_CACHE_DIR, HOST, PORT
from .database import init_db
from .tablo_client import tablo_manager
from .sync_service import sync_service
from .transcode import transcode_manager

from .routes import auth, shows, episodes, system, debug, guide, live


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    print("[Startup] Initializing Tablo SQLite database...")
    init_db()

    # If credentials/device already loaded, kick off an initial library sync in background
    # (sync_library starts the guide sync itself once it finishes)
    if tablo_manager.is_authenticated:
        print(f"[Startup] Found cached Tablo device: {tablo_manager.device.name} ({tablo_manager.device.local_url})")
        asyncio.create_task(sync_service.sync_library())
    else:
        print("[Startup] No authenticated Tablo device yet. Ready for login via web UI.")

    yield

    # Shutdown: clean up transcode sessions
    print("[Shutdown] Cleaning up stream sessions...")
    for sid in list(transcode_manager.sessions.keys()):
        transcode_manager.stop_session(sid)


app = FastAPI(
    title="Tablo Classic UI",
    description="Local 4th Gen Tablo Recordings Grid Manager",
    version="1.0.0",
    lifespan=lifespan
)

# No CORS middleware: the UI is served from this same origin, and allowing any
# origin would let arbitrary websites drive the API (e.g. delete recordings).


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

@app.get("/api/hls/{session_id}/{subpath:path}")
async def proxy_hls_stream(session_id: str, subpath: str, request: Request):
    """Proxy HLS segments and manifests with URL rewriting."""
    query_str = str(request.url.query)
    return await transcode_manager.proxy_hls_request(session_id, subpath, query_str)


@app.get("/api/transcoded/{session_id}/{filename:path}")
async def serve_transcoded_file(session_id: str, filename: str):
    """Serve transcoded HLS playlist and video segments."""
    file_path = safe_join(TRANSCODE_DIR, session_id, filename)
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
        return Response(
            content=file_path.read_bytes(),
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache, no-store",
                "Access-Control-Allow-Origin": "*",
                "Content-Disposition": "inline"
            }
        )

    return FileResponse(
        str(file_path),
        media_type="video/mp2t" if filename.endswith(".ts") else "application/octet-stream",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/downloads/{filename:path}")
async def serve_downloaded_mp4(filename: str):
    """Serve completed MP4 exports for download or browser playback."""
    file_path = safe_join(DOWNLOADS_DIR, filename)
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

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return Response(content="Tablo Classic UI is starting up...", media_type="text/plain")
    return FileResponse(
        str(index_file),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
