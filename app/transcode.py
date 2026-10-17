"""Transcoding, HLS streaming proxy, and MP4 background export manager."""

import os
import re
import sys
import uuid
import asyncio
import stat
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Any

import httpx
from starlette.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from .config import TRANSCODE_DIR, DOWNLOADS_DIR, FFMPEG_PATH
from .database import save_export_job


def force_rmtree(path: Path, quiet: bool = False) -> bool:
    """rmtree that also handles Windows read-only files/folders, which otherwise fail with Access Denied."""
    def _clear_readonly_and_retry(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    try:
        shutil.rmtree(path, onexc=_clear_readonly_and_retry)
        return True
    except Exception as e:
        if not quiet:
            print(f"[TranscodeManager] Could not remove {path}: {e}")
        return False


def remove_dir_with_retry(path: Path, attempts: int = 10):
    """Remove a session folder; if a segment is still locked (e.g. a player request in flight
    right after FFmpeg is killed), keep retrying in the background for a few seconds."""
    if force_rmtree(path, quiet=True):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        force_rmtree(path)
        return

    async def _retry():
        for _ in range(attempts):
            await asyncio.sleep(1)
            if not path.exists() or force_rmtree(path, quiet=True):
                return
        force_rmtree(path)  # final attempt logs the error; startup cleanup catches leftovers

    loop.create_task(_retry())


class StreamSession:
    def __init__(self, session_id: str, playlist_url: str):
        self.session_id = session_id
        self.playlist_url = playlist_url
        parsed = urlparse(playlist_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.created_at = datetime.now(timezone.utc)
        self.proc: Optional[subprocess.Popen] = None
        self.transcoded = False


class TranscodeManager:
    def __init__(self):
        self.sessions: Dict[str, StreamSession] = {}
        self.export_tasks: Dict[str, asyncio.Task] = {}
        self._http = httpx.AsyncClient(timeout=30)
        self.cleanup_stale_transcodes()

    def cleanup_stale_transcodes(self):
        """Wipe old transcode temp folders on startup."""
        try:
            if TRANSCODE_DIR.exists():
                for d in TRANSCODE_DIR.iterdir():
                    if d.is_dir():
                        force_rmtree(d)
        except Exception as e:
            print(f"[TranscodeManager] Cleanup notice: {e}")

    def create_session(self, playlist_url: str) -> StreamSession:
        session_id = uuid.uuid4().hex
        sess = StreamSession(session_id, playlist_url)
        self.sessions[session_id] = sess
        return sess

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        return self.sessions.get(session_id)

    def stop_session(self, session_id: str):
        sess = self.sessions.pop(session_id, None)
        if sess and sess.proc:
            try:
                sess.proc.kill()
                sess.proc.wait(timeout=2)
            except Exception:
                pass
        session_dir = TRANSCODE_DIR / session_id
        if session_dir.exists():
            remove_dir_with_retry(session_dir)

    def rewrite_manifest(self, manifest_text: str, session_id: str, playlist_url: str) -> str:
        """Rewrite relative HLS segment and playlist URLs to route through proxy."""
        playlist_base = playlist_url.rsplit("/", 1)[0] + "/"
        lines = []

        for line in manifest_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue

            # If line is an absolute URL
            if stripped.startswith(("http://", "https://")):
                parsed = urlparse(stripped)
                rel = parsed.path.lstrip("/")
                if parsed.query:
                    rel += "?" + parsed.query
            else:
                # Relative URL
                full_url = urljoin(playlist_base, stripped)
                parsed = urlparse(full_url)
                rel = parsed.path.lstrip("/")
                if parsed.query:
                    rel += "?" + parsed.query

            lines.append(f"/api/hls/{session_id}/{rel}")

        return "\n".join(lines)

    async def proxy_hls_request(self, session_id: str, subpath: str, query_string: str = "") -> Response:
        """Proxy HLS segments and manifests from Tablo device."""
        sess = self.get_session(session_id)
        if not sess:
            return Response(content="Session expired or not found", status_code=404)

        if subpath == "playlist.m3u8":
            target_url = sess.playlist_url
        else:
            target_url = f"{sess.base_url}/{subpath.lstrip('/')}"
            if query_string:
                target_url += f"?{query_string}"

        hls_type = "application/vnd.apple.mpegurl"

        try:
            resp = await self._http.get(target_url, timeout=15)
            if resp.status_code != 200:
                return Response(content=resp.content, status_code=resp.status_code)

            content_type = resp.headers.get("content-type", "")
            if "mpegurl" in content_type.lower() or subpath.endswith(".m3u8"):
                rewritten = self.rewrite_manifest(resp.text, session_id, target_url)
                return Response(
                    content=rewritten,
                    media_type=hls_type,
                    headers={
                        "Cache-Control": "no-cache, no-store",
                        "Access-Control-Allow-Origin": "*",
                        "Content-Disposition": "inline"
                    }
                )

            # Transport stream segment (.ts)
            return Response(
                content=resp.content,
                media_type="video/mp2t" if subpath.endswith(".ts") else content_type,
                headers={
                    "Cache-Control": "max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                    "Accept-Ranges": "bytes"
                }
            )
        except Exception as e:
            return Response(content=f"Proxy error: {e}", status_code=502)

    async def start_browser_transcode(self, session_id: str, input_url: str) -> str:
        """Transcode raw Tablo stream into H.264/AAC HLS for browser video player."""
        sess = self.get_session(session_id)
        if not sess:
            raise ValueError(f"Session {session_id} not found")

        session_dir = TRANSCODE_DIR / session_id
        session_dir.mkdir(exist_ok=True, parents=True)
        playlist_output = session_dir / "playlist.m3u8"

        cmd = [
            FFMPEG_PATH,
            "-y",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
            # Drop corrupt packets from the OTA feed instead of decoding garbage
            "-fflags", "+discardcorrupt",
            "-i", input_url,
            "-vf", "yadif",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p",
            # Stretch/pad audio to its timestamps so input gaps cause a short blip, not garbled sound
            "-af", "aresample=async=1",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-f", "hls",
            "-hls_time", "3",
            "-hls_list_size", "30",
            "-hls_segment_filename", str(session_dir / "%03d.ts"),
            "-hls_flags", "delete_segments+independent_segments",
            str(playlist_output)
        ]

        log_file = session_dir / "ffmpeg.log"
        # The child process keeps its own inherited handle; close ours right away
        with open(log_file, "w", encoding="utf-8") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(session_dir))
        sess.proc = proc
        sess.transcoded = True

        # Wait up to 12 seconds for playlist to be generated with at least 2 segments for smooth buffer
        for _ in range(30):
            if playlist_output.exists() and playlist_output.stat().st_size > 0:
                try:
                    text = playlist_output.read_text(encoding="utf-8")
                    if len(re.findall(r"\.ts", text)) >= 2:
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.4)

        return f"/api/transcoded/{session_id}/playlist.m3u8"

    def clean_filename(self, name: str) -> str:
        """Sanitize filename for Windows/macOS/Linux."""
        cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        return cleaned or "Tablo_Recording"

    async def start_mp4_export(self, episode: Dict[str, Any], playlist_url: str) -> str:
        """Background task: Pulls HLS stream via FFmpeg and saves as MP4 in ./downloads."""
        job_id = uuid.uuid4().hex[:10]

        # Generate standard filename: ShowName - SxxExx - Title.mp4
        show_title = self.clean_filename(episode.get("show_title", "Show"))
        season = episode.get("season_number", 0)
        ep_num = episode.get("episode_number", 0)
        ep_title = self.clean_filename(episode.get("title", ""))

        if season > 0 and ep_num > 0:
            prefix = f"{show_title} - S{season:02d}E{ep_num:02d}"
        elif ep_num > 0:
            prefix = f"{show_title} - E{ep_num:02d}"
        else:
            prefix = show_title

        filename = f"{prefix} - {ep_title}.mp4" if ep_title and ep_title != show_title else f"{prefix}.mp4"
        dest_path = DOWNLOADS_DIR / filename

        # Ensure unique filename if already exists
        counter = 1
        base_stem = dest_path.stem
        while dest_path.exists():
            dest_path = DOWNLOADS_DIR / f"{base_stem} ({counter}).mp4"
            counter += 1

        job_info = {
            "job_id": job_id,
            "episode_id": episode.get("id"),
            "title": f"{show_title} (S{season:02d}E{ep_num:02d})",
            "filename": dest_path.name,
            "filepath": str(dest_path),
            "status": "downloading",
            "progress": 0.0,
            "file_size": 0,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        save_export_job(job_info)

        # Launch async worker
        task = asyncio.create_task(self._run_ffmpeg_export(job_id, playlist_url, dest_path, episode.get("duration", 0)))
        self.export_tasks[job_id] = task

        return job_id

    async def _run_ffmpeg_export(self, job_id: str, playlist_url: str, output_path: Path, expected_duration: int):
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
            # Cap reads at 2x real time: unthrottled exports pull ~6.5x and starve
            # live TV / playback streams sharing the Tablo
            "-readrate", "2",
            "-i", playlist_url,
            # Copy video stream directly for zero loss & max speed, convert audio to aac for standard MP4 playback
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        print(f"[ExportWorker] Starting export {job_id} -> {output_path.name}")
        # Send FFmpeg's chatty stderr to a log file instead of an unread pipe,
        # which would fill up and stall long exports
        log_path = TRANSCODE_DIR / f"export_{job_id}.log"
        proc = None
        try:
            with open(log_path, "w", encoding="utf-8") as log_f:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f)

            # Poll progress while process is running
            while proc.poll() is None:
                await asyncio.sleep(2)
                size = output_path.stat().st_size if output_path.exists() else 0
                # Estimate progress if expected duration is known (approx 2GB per hour)
                est_bytes = max(expected_duration * 500_000, 10_000_000) if expected_duration else 500_000_000
                progress = min(round((size / est_bytes) * 90, 1), 95.0)

                save_export_job({
                    "job_id": job_id,
                    "status": "downloading",
                    "progress": progress,
                    "file_size": size
                })

            try:
                stderr = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                stderr = ""
            if proc.returncode == 0 and output_path.exists():
                size = output_path.stat().st_size
                print(f"[ExportWorker] Export {job_id} completed successfully ({round(size / 1024**2, 1)} MB)")
                save_export_job({
                    "job_id": job_id,
                    "status": "completed",
                    "progress": 100.0,
                    "file_size": size,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                })
            else:
                err_msg = stderr[-400:] if stderr else f"FFmpeg exited with code {proc.returncode}"
                print(f"[ExportWorker] Export {job_id} failed: {err_msg}")
                save_export_job({
                    "job_id": job_id,
                    "status": "failed",
                    "error": err_msg,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                })
        except Exception as e:
            print(f"[ExportWorker] Export exception: {e}")
            save_export_job({
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
        finally:
            try:
                log_path.unlink(missing_ok=True)
            except Exception:
                pass


transcode_manager = TranscodeManager()
