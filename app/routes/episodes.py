"""Episode actions: playback, transcoding, VLC m3u, MP4 export, and deletion."""

import asyncio
import json
import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import List, Optional

from ..database import (
    get_episode_by_id,
    get_show_by_id,
    delete_episode,
    recalculate_show_stats,
    set_episode_progress,
    get_in_progress_episodes,
    set_episode_protected,
)
from ..tablo_client import tablo_manager
from ..transcode import transcode_manager
from .. import previews

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


class BulkDeleteRequest(BaseModel):
    episode_ids: List[str]


class ProgressRequest(BaseModel):
    position: int = Field(ge=0)


class WatchedRequest(BaseModel):
    watched: bool


class ProtectRequest(BaseModel):
    protected: bool


@router.get("/in_progress")
async def list_in_progress():
    """Partly watched recordings, for 'Continue watching'."""
    return {"episodes": get_in_progress_episodes()}


@router.post("/{episode_id}/progress")
async def save_progress(episode_id: str, req: ProgressRequest):
    """Save the resume point on the Tablo (so the TV app resumes there too)."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    resp = await tablo_manager.request_recording("PATCH", ep["path"], json.dumps({"position": req.position}))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}")
    set_episode_progress(ep["id"], position=req.position)
    return {"success": True, "position": req.position}


@router.post("/{episode_id}/watched")
async def set_watched(episode_id: str, req: WatchedRequest):
    """Mark a recording watched or unwatched on the Tablo."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    # Clear the resume point either way: finished, or explicitly reset to unwatched
    body = {"watched": True} if req.watched else {"watched": False, "position": 0}
    resp = await tablo_manager.request_recording("PATCH", ep["path"], json.dumps(body))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}")
    if not req.watched:
        set_episode_progress(ep["id"], position=0)
    set_episode_progress(ep["id"], watched=req.watched)
    return {"success": True, "watched": req.watched, "show": get_show_by_id(ep["show_id"])}


@router.get("/{episode_id}/previews")
async def preview_times(episode_id: str):
    """Times (seconds) of the timeline preview frames, once fetched (empty until then)."""
    return {"times": previews.times(episode_id) or []}


@router.get("/{episode_id}/previews/{n}")
async def preview_frame(episode_id: str, n: int):
    data = previews.frame(episode_id, n)
    if data is None:
        raise HTTPException(status_code=404, detail="No such preview frame")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{episode_id}/commercials")
async def episode_commercials(episode_id: str):
    """Commercial breaks found in this recording ([] while not analyzed), and the skip setting."""
    from .. import commercials
    from ..database import get_commercials
    from ..settings import load_settings
    from .. import dropouts
    found = get_commercials([episode_id]).get(episode_id)
    drops = dropouts.get(episode_id)
    settings = load_settings()
    return {"status": found["status"] if found else ("analyzing" if commercials.status["current"] == episode_id else None),
            "breaks": found["breaks"] if found else [],
            "auto_skip": bool(settings.get("skip_commercials")),
            # Signal dropouts (recordings the Tablo flagged as not clean; app/dropouts.py)
            "dropouts": drops["spans"] if drops else [],
            "auto_skip_dropouts": bool(settings.get("skip_dropouts"))}


@router.post("/{episode_id}/find_commercials")
async def find_commercials(episode_id: str):
    """Find the commercial breaks in just this recording (in the background, when nothing is playing)."""
    from .. import commercials
    from ..database import get_commercials
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.get("recording_state") != "finished":
        raise HTTPException(status_code=400, detail="This recording isn't finished yet")
    if get_commercials([episode_id]).get(episode_id, {}).get("status") == "done":
        return {"queued": False, "ahead": 0}
    commercials.queue_episode(episode_id)
    queue = commercials.pending()
    return {"queued": True, "ahead": next((i for i, e in enumerate(queue) if e["id"] == episode_id), 0)}


@router.get("/{episode_id}/rerecord")
async def rerecord_options(episode_id: str):
    """Upcoming airings of the same episode as this (failed or partial) recording."""
    from .. import rerecord
    found = rerecord.alternatives(episode_id)
    if not found:
        raise HTTPException(status_code=404, detail="Episode not found")
    return {"airings": found["airings"]}


@router.post("/{episode_id}/protected")
async def set_protected(episode_id: str, req: ProtectRequest):
    """Protect a recording on the Tablo (it's then never deleted to make room or by cleanup), or unprotect it."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    resp = await tablo_manager.request_recording("PATCH", ep["path"], json.dumps({"protected": req.protected}))
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"Tablo error {resp.status_code}")
    # The Tablo answers with the updated recording; make sure it took the change
    try:
        echoed = (resp.json().get("user_info") or {}).get("protected")
    except ValueError:
        echoed = None
    if echoed is not None and bool(echoed) != req.protected:
        raise HTTPException(status_code=502, detail="The Tablo didn't accept the change")
    set_episode_protected(ep["id"], req.protected)
    return {"success": True, "protected": req.protected}


GONE_MESSAGE = "This recording was deleted from your Tablo, so it's been taken out of your library"


async def _deleted_elsewhere(error: Exception, ep: dict) -> bool:
    """The Tablo answered "not found" to playing a recording: deleted from another app since the last
    sync. Checked once more by asking for the recording itself, then taken out of the library so it
    doesn't stay in Continue watching and the show's list until the next sync."""
    if not (isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 404):
        return False
    try:
        resp = await tablo_manager.request_local("GET", ep["path"])
    except Exception:
        return False
    if resp.status_code != 404:
        return False
    print(f"[Watch] {ep['path']} is no longer on the Tablo; removed from the library")
    delete_episode(ep["id"])
    return True


@router.post("/{episode_id}/watch")
async def watch_episode(
    episode_id: str,
    request: Request,
    transcode: bool = Query(default=True, description="Transcode for browser video player"),
    start: int = Query(default=0, ge=0, description="Resume point in seconds"),
):
    """Obtain stream URL from Tablo and initialize proxy/transcoder session."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found in database")

    airing_path = ep["path"]
    try:
        watch_data = await tablo_manager.get_airing_watch_url(airing_path)
    except httpx.TransportError as e:
        # Refused or timed out: the Tablo sometimes stops answering for a minute or so
        print(f"[Watch] Tablo didn't answer the watch request for {airing_path}: {e!r}")
        raise HTTPException(status_code=503, detail=tablo_manager.UNREACHABLE_MESSAGE)
    except Exception as e:
        print(f"[Watch] Watch request for {airing_path} failed: {e!r}")
        if await _deleted_elsewhere(e, ep):
            raise HTTPException(status_code=410, detail=GONE_MESSAGE)
        raise HTTPException(status_code=502, detail=f"Failed to start watch session on Tablo: {e or type(e).__name__}")

    playlist_url = watch_data.get("playlist_url")
    if not playlist_url:
        raise HTTPException(status_code=502, detail="No playlist_url received from Tablo")

    sess = transcode_manager.create_session(playlist_url)
    sess.tablo_token = watch_data.get("token")
    # The whole recording's timeline previews, from the Tablo (one small file, cached per episode)
    if watch_data.get("bif_url_hd"):
        asyncio.create_task(previews.fetch(ep["id"], watch_data["bif_url_hd"], ep.get("recording_state") == "finished"))

    if transcode:
        try:
            stream_url = await transcode_manager.start_browser_transcode(sess.session_id, playlist_url, start=start, live=False)
        except Exception as e:
            print(f"Transcode failed, falling back to direct proxy: {e}")
            stream_url = f"/api/hls/{sess.session_id}/playlist.m3u8"
    else:
        stream_url = f"/api/hls/{sess.session_id}/playlist.m3u8"

    return {
        "session_id": sess.session_id,
        "proxy_url": f"/api/hls/{sess.session_id}/playlist.m3u8",
        "stream_url": stream_url,
        "transcoded": transcode,
        "raw_playlist_url": playlist_url
    }


@router.get("/{episode_id}/playlist.m3u")
async def download_m3u_playlist(episode_id: str, request: Request):
    """Generate and return an M3U playlist file for instant playback in VLC / MPV / IINA."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    airing_path = ep["path"]
    watch_data = await tablo_manager.get_airing_watch_url(airing_path)
    playlist_url = watch_data.get("playlist_url")
    if not playlist_url:
        raise HTTPException(status_code=502, detail="No playlist_url received from Tablo")

    # Create proxy session so client on any machine on LAN can play it
    sess = transcode_manager.create_session(playlist_url)
    base_host = str(request.base_url).rstrip("/")
    stream_link = f"{base_host}/api/hls/{sess.session_id}/playlist.m3u8"

    show_title = ep.get("show_title", "Show")
    ep_title = ep.get("title", "")
    s_num = ep.get("season_number", 0)
    e_num = ep.get("episode_number", 0)
    display_title = f"{show_title} - S{s_num:02d}E{e_num:02d} - {ep_title}" if s_num and e_num else f"{show_title} - {ep_title}"

    m3u_content = f"#EXTM3U\n#EXTINF:-1,{display_title}\n{stream_link}\n"
    filename = f"{transcode_manager.clean_filename(display_title)}.m3u"

    return Response(
        content=m3u_content,
        media_type="application/x-mpegurl",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )


@router.post("/{episode_id}/export")
async def export_episode_mp4(episode_id: str):
    """Trigger background MP4 export via FFmpeg to ./downloads."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    job_id = await transcode_manager.start_mp4_export(ep, tablo_manager.playlist_getter(ep["path"]))
    return {
        "status": "started",
        "job_id": job_id,
        "message": "Export task started in background."
    }


class ExportBatchRequest(BaseModel):
    episode_ids: List[str]


@router.post("/export_batch")
async def export_batch(req: ExportBatchRequest):
    """Queue MP4 exports of several recordings (they run one after another)."""
    jobs = []
    for episode_id in req.episode_ids:
        ep = get_episode_by_id(episode_id)
        if ep:
            jobs.append(await transcode_manager.start_mp4_export(ep, tablo_manager.playlist_getter(ep["path"])))
    return {"status": "started", "job_ids": jobs, "count": len(jobs)}


@router.delete("/{episode_id}")
async def delete_single_episode(episode_id: str):
    """Send signed DELETE to Tablo hardware and remove from SQLite cache."""
    ep = get_episode_by_id(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    path = ep["path"]
    show_id = ep["show_id"]

    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device is not connected")

    try:
        ok = await tablo_manager.delete_airing(path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Tablo delete failed: {e}")
    if not ok:
        raise HTTPException(status_code=502, detail="Tablo refused to delete the recording")

    # Device confirmed: remove from local database and update show stats
    delete_episode(episode_id)
    updated_show = get_show_by_id(show_id)

    return {
        "success": True,
        "deleted_id": episode_id,
        "show": updated_show
    }


@router.post("/bulk_delete")
async def bulk_delete_episodes(req: BulkDeleteRequest):
    """Delete multiple episodes at once."""
    deleted = []
    errors = []
    affected_shows = set()

    for ep_id in req.episode_ids:
        ep = get_episode_by_id(ep_id)
        if not ep:
            continue
        path = ep["path"]
        show_id = ep["show_id"]
        affected_shows.add(show_id)

        try:
            if not tablo_manager.is_authenticated:
                raise RuntimeError("Tablo device is not connected")
            if not await tablo_manager.delete_airing(path):
                raise RuntimeError("Tablo refused to delete the recording")
            delete_episode(ep_id)
            deleted.append(ep_id)
        except Exception as e:
            errors.append(f"Failed deleting {ep_id}: {e}")

    updated_shows = [get_show_by_id(sid) for sid in affected_shows if get_show_by_id(sid)]

    return {
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "errors": errors,
        "updated_shows": updated_shows
    }
