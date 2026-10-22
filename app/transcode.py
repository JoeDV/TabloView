"""Transcoding, HLS streaming proxy, and MP4 background export manager."""

import os
import re
import sys
import uuid
import asyncio
import stat
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

import httpx
from starlette.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from . import childproc, encoders
from .config import TRANSCODE_DIR, FFMPEG_PATH
from .database import save_export_job
from .settings import load_settings, exports_dir

# The packaged app has no console, so Windows would open a console window for each ffmpeg it starts
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

HLS_SEGMENT_SECONDS = 3
# How many times one stream's FFmpeg is restarted after dying mid-stream (see _supervise)
MAX_STREAM_RESTARTS = 4
# Live TV keeps this much behind the live point, for pause and rewind (about 1-1.5 GB on disk)
LIVE_REWIND_MINUTES = 30
# Recordings: a small preview frame every this many seconds, for the timeline. Named by position in
# the recording (p01234.jpg = 1234 x PREVIEW_SECONDS), so a restart or a resume point fits in.
PREVIEW_SECONDS = 5
# MP4 exports: no progress for this long means the Tablo stopped sending (see _stop_stalled_export);
# past this share of the recording, what arrived is kept rather than thrown away
EXPORT_STALL_SECONDS = 60
# Exports normally read through TabloView, which sets the pace as they go (app/export_pace.py). If that
# can't be set up, they read the recording directly at twice real time (faster starves live TV and
# playback sharing the Tablo: unthrottled is about 6.5x).
EXPORT_READRATE = 2
EXPORT_NEAR_END = 0.9


def run_at_full_speed(proc: subprocess.Popen) -> None:
    """Opt FFmpeg out of Windows 11 'efficiency mode' (EcoQoS). Started from a windowless background
    app it can be throttled to slow cores and low clocks, which made live conversion fall below real
    time even with idle CPU to spare."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        class PowerThrottlingState(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]

        # ProcessPowerThrottling = 4; control EXECUTION_SPEED (1) and set it off (state 0)
        state = PowerThrottlingState(1, 1, 0)
        ctypes.windll.kernel32.SetProcessInformation(int(proc._handle), 4, ctypes.byref(state), ctypes.sizeof(state))
    except Exception as e:
        print(f"[Transcode] Couldn't turn off power throttling for FFmpeg: {e}")


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
        self.encoder: Optional[str] = None  # what converted it, e.g. "Intel Quick Sync" or "copy"
        self.stopped = False  # set when the player closes it, so the supervisor doesn't restart it
        self.tablo_token: Optional[str] = None  # the Tablo's watch session, ended when this stops
        self.channel_id: Optional[str] = None  # live TV: the channel (to tell TabloView's own tuners apart)
        self.supervisor: Optional[asyncio.Task] = None
        self.reception = None  # live antenna channels: picture quality meter (app/reception.py)
        self.reception_task: Optional[asyncio.Task] = None


class TranscodeManager:
    def __init__(self):
        self.sessions: Dict[str, StreamSession] = {}
        self.export_tasks: Dict[str, asyncio.Task] = {}
        # Exports run one at a time (created on first use, inside the event loop)
        self._export_slot: Optional[asyncio.Semaphore] = None
        self.export_procs: Dict[str, subprocess.Popen] = {}  # running exports' FFmpeg, by job
        # Live channels TabloView stopped, and when: the Tablo keeps the channel on the tuner a little
        # longer, and the tuner list shouldn't call that "another app"
        self.recently_closed: Dict[str, float] = {}
        self.cancelled_exports: set = set()
        # Watch sessions being ended on the Tablo; tuning waits for these so the old channel's
        # tuner is given back before the new channel asks for one
        self._ending: set = set()
        # Smooth motion couldn't keep up with live TV on this PC: live channels use standard motion
        # until TabloView restarts (recordings aren't affected: they don't have to keep pace)
        self.smooth_live_too_slow = False
        self._http = httpx.AsyncClient(timeout=30)
        self.cleanup_stale_transcodes()

    def cleanup_stale_transcodes(self):
        """Wipe old transcode temp folders on startup. A folder something is still writing to (changed
        in the last couple of minutes) belongs to a session another TabloView process is playing right
        now: left alone. Wiping it deleted a live stream's rewind (2026-10-20, twice)."""
        try:
            if TRANSCODE_DIR.exists():
                for d in TRANSCODE_DIR.iterdir():
                    if d.is_dir() and not self._in_use(d):
                        force_rmtree(d)
        except Exception as e:
            print(f"[TranscodeManager] Cleanup notice: {e}")

    @staticmethod
    def _in_use(folder: Path, recent_seconds: float = 120) -> bool:
        """Anything in folder modified within recent_seconds (an FFmpeg writing a stream's pieces)."""
        cutoff = time.time() - recent_seconds
        try:
            return any(f.stat().st_mtime > cutoff for f in folder.iterdir())
        except OSError:
            return True  # can't tell: leave it

    def create_session(self, playlist_url: str) -> StreamSession:
        session_id = uuid.uuid4().hex
        sess = StreamSession(session_id, playlist_url)
        self.sessions[session_id] = sess
        return sess

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        return self.sessions.get(session_id)

    def start_measure(self, sess: StreamSession, input_url: str) -> None:
        """Antenna helper: decode a live channel only to measure it (no video for a player), so it's
        light on the PC; the picture quality meter follows its log as for live TV."""
        session_dir = TRANSCODE_DIR / sess.session_id
        session_dir.mkdir(exist_ok=True, parents=True)
        cmd = [FFMPEG_PATH, "-y", "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
               "-fflags", "+discardcorrupt", "-i", input_url, "-map", "0:v:0", "-f", "null", "-"]
        with open(session_dir / "ffmpeg.log", "w", encoding="utf-8") as f:
            sess.proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(session_dir),
                                         creationflags=NO_WINDOW, **childproc.popen_kwargs())
        childproc.tie_to_app(sess.proc)
        run_at_full_speed(sess.proc)  # throttled, it falls behind live TV and looks like lost frames
        sess.encoder = "measure only"
        self.start_reception(sess)

    def start_reception(self, sess: StreamSession) -> None:
        """Follow a live antenna channel's FFmpeg log once a second for the picture quality meter."""
        from .reception import Meter
        sess.reception = Meter(TRANSCODE_DIR / sess.session_id / "ffmpeg.log")

        async def follow():
            while not sess.stopped:
                sess.reception.sample()
                await asyncio.sleep(1)

        sess.reception_task = asyncio.create_task(follow())

    async def wait_for_ended_sessions(self, timeout: float = 5.0) -> None:
        """Wait (briefly) until the Tablo has been told about every watch session just stopped."""
        if self._ending:
            await asyncio.wait(list(self._ending), timeout=timeout)

    def stop_session(self, session_id: str):
        sess = self.sessions.pop(session_id, None)
        if sess:
            sess.stopped = True
            if sess.channel_id:
                self.recently_closed[sess.channel_id] = time.time()
            if sess.supervisor:
                sess.supervisor.cancel()
            if sess.reception_task:
                sess.reception_task.cancel()
            if sess.tablo_token:
                # Free the tuner on the Tablo now rather than when its session times out
                from .tablo_client import tablo_manager
                try:
                    task = asyncio.get_running_loop().create_task(tablo_manager.end_watch_session(sess.tablo_token))
                    self._ending.add(task)
                    task.add_done_callback(self._ending.discard)
                except RuntimeError:
                    pass  # no event loop (shutting down)
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

    async def probe_video_codec(self, url: str) -> Optional[str]:
        """The stream's video codec (e.g. 'h264', 'mpeg2video'), or None if it can't be read quickly."""
        def run() -> str:
            try:
                return subprocess.run([FFMPEG_PATH, "-hide_banner", "-i", url], capture_output=True, text=True,
                                      timeout=10, creationflags=NO_WINDOW).stderr
            except Exception:
                return ""
        m = re.search(r"Video: (\w+)", await asyncio.to_thread(run))
        return m.group(1) if m else None

    def _video_plan(self, passthrough: bool) -> Dict[str, Any]:
        """Encoder and filters from the Playback settings (see app/encoders.py)."""
        settings = load_settings()
        quality = settings.get("video_quality") or "auto"
        if passthrough:
            return {"encoder": None, "smooth": False, "quality": quality}
        enc = encoders.choose(quality)
        # Smooth motion (60 fps) is opt-in: it works the graphics chip twice as hard. (Its Quick Sync
        # failures, 4 of 6 one-minute runs, were fixed by encoders.QSV_STABLE: 2 of 2 two-minute runs clean)
        smooth = bool(settings.get("smooth_motion"))
        return {"encoder": enc, "smooth": smooth and quality != "fastest", "quality": quality}

    def _build_cmd(self, input_url: str, start: int, live: bool, plan: Dict[str, Any], session_dir: Path,
                   resume: bool = False) -> List[str]:
        if live:
            # Keep the last LIVE_REWIND_MINUTES so live TV can be paused and rewound
            read_args = []
            hls_args = ["-hls_list_size", str(LIVE_REWIND_MINUTES * 60 // HLS_SEGMENT_SECONDS),
                        "-hls_flags", "delete_segments+independent_segments"]
        else:
            # Stay well ahead of playback without racing through the whole file: unthrottled, a
            # recording transcodes several times faster than real time and starves a live stream
            # playing at the same time
            read_args = ["-readrate", "2", "-readrate_initial_burst", "30"]
            # No end marker from FFmpeg: it also writes one when it crashes, and a player that sees it
            # stops for good. _supervise adds it when the recording has really been converted to the end.
            hls_args = ["-hls_list_size", "0", "-hls_playlist_type", "event", "-hls_flags", "independent_segments+omit_endlist"]
        if resume:
            # Continuing after FFmpeg died: add to the same playlist (FFmpeg numbers on from its last
            # segment) with a discontinuity marker so the player handles the restarted timestamps
            i = hls_args.index("-hls_flags") + 1
            hls_args[i] += "+append_list+discont_start"

        enc = plan["encoder"]
        if enc is None:
            # Already browser-friendly H.264 (streaming channels): repackage without re-encoding
            video = ["-c:v", "copy"]
        else:
            # Deinterlace only frames that are interlaced (1080i), leaving 720p/progressive alone;
            # send_field turns each field into a frame (60 fps) for smooth motion. It also doubles
            # sources that are already 60 fps (720p), so cap the result at 59.94.
            deint = ("bwdif=mode=send_field:deint=interlaced,fps=60000/1001" if plan["smooth"]
                     else "bwdif=mode=send_frame:deint=interlaced")
            video = ["-vf", deint, *enc["args"], "-pix_fmt", enc["pix_fmt"],
                     # A keyframe every segment: segments start cleanly and playback starts sooner
                     "-force_key_frames", f"expr:gte(t,n_forced*{HLS_SEGMENT_SECONDS})"]

        return [
            FFMPEG_PATH,
            "-y",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
            # Drop corrupt packets from the OTA feed instead of decoding garbage
            "-fflags", "+discardcorrupt",
            *(["-ss", str(int(start))] if start and start > 0 else []),
            *read_args,
            "-i", input_url,
            *video,
            # Stretch/pad audio to its timestamps so input gaps cause a short blip, not garbled sound.
            # 5.1 is mixed to stereo with the centre (dialogue) channel at full level and the
            # surrounds lowered, so speech isn't drowned out
            "-af", "aresample=async=1:ochl=stereo:clev=1.0:slev=0.6",
            "-c:a", "aac", "-b:a", "192k", "-ac", "2",
            "-f", "hls",
            "-hls_time", str(HLS_SEGMENT_SECONDS),
            *hls_args,
            "-hls_segment_filename", str(session_dir / "%05d.ts"),
            str(session_dir / "playlist.m3u8"),
            *([] if live else self._preview_output(start, session_dir)),
        ]

    @staticmethod
    def _preview_output(start: int, session_dir: Path) -> List[str]:
        """A second output: timeline preview frames from the video FFmpeg is decoding anyway (scaled
        down, so interlacing doesn't show). Nothing extra is read from the Tablo."""
        return ["-map", "0:v:0", "-vf", f"fps=1/{PREVIEW_SECONDS}:round=down,scale=256:-2", "-q:v", "6",
                "-start_number", str(int(start or 0) // PREVIEW_SECONDS), "-f", "image2",
                str(session_dir / "p%05d.jpg")]

    async def start_browser_transcode(self, session_id: str, input_url: str, start: int = 0, live: bool = True,
                                      passthrough: bool = False) -> str:
        """Convert a Tablo stream into H.264/AAC HLS for the browser player.

        live=True keeps a rolling ~90 s window (live TV). For recordings (live=False) every segment is
        kept so the player can seek anywhere already converted, and `start` (seconds) resumes mid-show.
        passthrough=True copies the video as is (for streams that are already H.264).
        If a graphics-chip encoder or the copy fails before producing anything, it retries on the CPU.
        """
        sess = self.get_session(session_id)
        if not sess:
            raise ValueError(f"Session {session_id} not found")

        session_dir = TRANSCODE_DIR / session_id
        session_dir.mkdir(exist_ok=True, parents=True)
        playlist_output = session_dir / "playlist.m3u8"

        plan = await asyncio.to_thread(self._video_plan, passthrough)
        if live and plan["smooth"] and self.smooth_live_too_slow:
            plan = {**plan, "smooth": False}  # this PC couldn't keep up with it earlier (see _supervise)
        for attempt in range(2):
            cmd = self._build_cmd(input_url, start, live, plan, session_dir)
            # The child process keeps its own inherited handle; close ours right away
            with open(session_dir / "ffmpeg.log", "w", encoding="utf-8") as f:
                proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(session_dir),
                                        creationflags=NO_WINDOW, **childproc.popen_kwargs())
            childproc.tie_to_app(proc)
            run_at_full_speed(proc)
            sess.proc = proc
            sess.transcoded = True
            sess.encoder = "copy" if plan["encoder"] is None else plan["encoder"]["label"]

            # Wait up to 12 seconds for at least 2 segments, for a smooth start
            ready = False
            for _ in range(30):
                if playlist_output.exists() and playlist_output.stat().st_size > 0:
                    try:
                        if len(re.findall(r"\.ts", playlist_output.read_text(encoding="utf-8"))) >= 2:
                            ready = True
                            break
                    except Exception:
                        pass
                if proc.poll() is not None:
                    break
                await asyncio.sleep(0.4)

            failed = not ready and proc.poll() not in (None, 0)
            if not failed or attempt == 1:
                break
            # Fall back to CPU encoding (the hardware encoder or the copy didn't work for this stream)
            enc = plan["encoder"]
            if enc is not None and enc["hardware"]:
                encoders.mark_failed(enc["name"])
            elif enc is not None:
                break  # already on the CPU: nothing else to try
            print(f"[Transcode] {sess.encoder} failed for session {session_id}; retrying on the CPU")
            plan = {**plan, "encoder": encoders.cpu_fallback(plan["quality"]),
                    "smooth": plan["smooth"] and plan["encoder"] is not None}
            for old in session_dir.glob("*.ts"):
                old.unlink(missing_ok=True)
            playlist_output.unlink(missing_ok=True)

        print(f"[Transcode] Session {session_id[:8]}: {sess.encoder}{', 60 fps' if plan['smooth'] else ''}")
        if ready:
            sess.supervisor = asyncio.create_task(self._supervise(sess, input_url, start, live, plan, session_dir))
        return f"/api/transcoded/{session_id}/playlist.m3u8"

    @staticmethod
    def _playlist_seconds(session_dir: Path) -> float:
        """Seconds converted so far, from the session's playlist."""
        try:
            text = (session_dir / "playlist.m3u8").read_text(encoding="utf-8")
        except OSError:
            return 0.0
        return sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", text))

    async def _supervise(self, sess: StreamSession, input_url: str, start: int, live: bool,
                         plan: Dict[str, Any], session_dir: Path) -> None:
        """Keep a stream going if FFmpeg dies part way through: a graphics-chip encoder can fail at
        random ("device failed"), and the Tablo sometimes stops sending for a moment. FFmpeg is
        restarted where it stopped, adding to the same playlist, so the player (which has several
        seconds buffered) carries on. A second failure of a hardware encoder switches this stream to
        the CPU's fastest setting."""
        restarts = 0
        while restarts < MAX_STREAM_RESTARTS:
            while sess.proc.poll() is None:
                await asyncio.sleep(1)
                if live and plan["smooth"] and self._falling_behind(session_dir):
                    # Live TV arrives in real time; converting slower than that means the picture falls
                    # further and further behind (WTHR with Smooth motion: 0.5x, 29 of 60 frames a
                    # second). Carry on in standard motion: restarted below, adding to the same playlist.
                    print(f"[Transcode] Session {sess.session_id[:8]}: Smooth motion can't keep up with live TV "
                          f"on this PC; using standard motion for live TV")
                    self.smooth_live_too_slow = True
                    plan = {**plan, "smooth": False}
                    sess.proc.kill()
                    sess.proc.wait(timeout=5)
            if sess.stopped or self.sessions.get(sess.session_id) is not sess:
                return
            if sess.proc.returncode == 0:
                if not live:
                    self._end_playlist(session_dir)
                return
            restarts += 1
            enc = plan["encoder"]
            if enc is not None and enc["hardware"] and restarts >= 2:
                plan = {**plan, "encoder": encoders.choose("fastest"), "smooth": False}
            done = self._playlist_seconds(session_dir)
            resume_at = start if live else int(start + done)
            print(f"[Transcode] Session {sess.session_id[:8]}: FFmpeg stopped (code {sess.proc.returncode}); "
                  f"restart {restarts} with {plan['encoder']['label'] if plan['encoder'] else 'copy'}"
                  f"{'' if live else f' at {resume_at} s'}")
            cmd = self._build_cmd(input_url, resume_at, live, plan, session_dir, resume=True)
            with open(session_dir / "ffmpeg.log", "a", encoding="utf-8") as f:
                f.write(f"\n===== restart {restarts} =====\n")
                f.flush()
                sess.proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(session_dir),
                                             creationflags=NO_WINDOW, **childproc.popen_kwargs())
            childproc.tie_to_app(sess.proc)
            run_at_full_speed(sess.proc)
            sess.encoder = "copy" if plan["encoder"] is None else plan["encoder"]["label"]
            # A restart that dies straight away counts against the limit too
            await asyncio.sleep(3)

    @staticmethod
    def _falling_behind(session_dir: Path) -> bool:
        """FFmpeg's own progress report: after 30 s, converting at under 85% of real time on average.
        (A live channel that keeps up reads 0.95-1.0x once the first few seconds are past.)"""
        try:
            with open(session_dir / "ffmpeg.log", "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 4096))
                tail = f.read().decode("utf-8", errors="replace")
        except OSError:
            return False
        m = re.findall(r"speed=\s*([\d.]+)x\s+elapsed=(\d+):(\d+):([\d.]+)", tail)
        if not m:
            return False
        speed, h, mins, secs = m[-1]
        elapsed = int(h) * 3600 + int(mins) * 60 + float(secs)
        return elapsed >= 30 and float(speed) < 0.85

    @staticmethod
    def _end_playlist(session_dir: Path) -> None:
        """The recording is converted to the end: tell the player there's nothing more coming."""
        playlist = session_dir / "playlist.m3u8"
        try:
            text = playlist.read_text(encoding="utf-8")
            if "#EXT-X-ENDLIST" not in text:
                playlist.write_text(text.rstrip("\n") + "\n#EXT-X-ENDLIST\n", encoding="utf-8")
        except OSError as e:
            print(f"[Transcode] Couldn't finish the playlist: {e}")

    def clean_filename(self, name: str) -> str:
        """Sanitize filename for Windows/macOS/Linux."""
        cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        return cleaned or "Tablo_Recording"

    async def start_mp4_export(self, episode: Dict[str, Any], get_playlist_url) -> str:
        """Queue an MP4 export to the downloads folder. Exports run one at a time (each pulls a stream
        from the Tablo); get_playlist_url() is awaited when this one's turn comes, so the Tablo's
        watch session is fresh."""
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
        folder = exports_dir()
        dest_path = folder / filename

        # Ensure unique filename if already exists
        counter = 1
        base_stem = dest_path.stem
        while dest_path.exists():
            dest_path = folder / f"{base_stem} ({counter}).mp4"
            counter += 1

        job_info = {
            "job_id": job_id,
            "episode_id": episode.get("id"),
            "title": f"{show_title} (S{season:02d}E{ep_num:02d})",
            "filename": dest_path.name,
            "filepath": str(dest_path),
            "status": "pending",
            "progress": 0.0,
            "file_size": 0,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        save_export_job(job_info)

        # The recording's own length (the Tablo pads its time slot by about 75 s), for progress and
        # for telling a stall near the end from one partway through
        length = int(episode.get("actual_duration") or episode.get("duration") or 0)
        task = asyncio.create_task(self._queued_export(job_id, get_playlist_url, dest_path, length))
        self.export_tasks[job_id] = task

        return job_id

    def cancel_export(self, job_id: str) -> bool:
        """Stop an export that's running (its FFmpeg is stopped and the partial file removed) or still
        waiting its turn. False if it's already finished."""
        if job_id in self.export_procs:
            self.cancelled_exports.add(job_id)  # _run_ffmpeg_export stops it within 2 s
            return True
        task = self.export_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            save_export_job({"job_id": job_id, "status": "cancelled", "progress": 0.0,
                             "completed_at": datetime.now(timezone.utc).isoformat()})
            return True
        return False

    async def _queued_export(self, job_id: str, get_playlist_url, output_path: Path, expected_duration: int):
        if self._export_slot is None:
            self._export_slot = asyncio.Semaphore(1)
        async with self._export_slot:
            try:
                playlist_url = await get_playlist_url()
            except Exception as e:
                save_export_job({"job_id": job_id, "status": "failed", "error": f"Couldn't start it on the Tablo: {e}",
                                 "completed_at": datetime.now(timezone.utc).isoformat()})
                return
            fmt = load_settings().get("export_format") or "smaller"
            enc = encoders.for_export(encoders.choose("auto")) if fmt == "smaller" else None
            ok = await self._run_ffmpeg_export(job_id, playlist_url, output_path, expected_duration, enc,
                                               last_try=not (enc and enc["hardware"]))
            if not ok and enc and enc["hardware"]:
                # The graphics chip gave up on this one: do it on the CPU instead (slower)
                encoders.mark_failed(enc["name"])
                await self._run_ffmpeg_export(job_id, playlist_url, output_path, expected_duration,
                                              encoders.for_export(encoders.cpu_fallback()), last_try=True)

    @staticmethod
    def export_cmd(playlist_url: str, part_path: Path, enc: Optional[Dict[str, Any]],
                   readrate: Optional[float] = EXPORT_READRATE) -> List[str]:
        """enc None: copy the broadcast video as is (largest, exact). Otherwise convert to H.264
        (deinterlaced, like playback), which is usually much smaller.

        Written as MPEG-TS first (part_path), then re-packaged as the MP4 (remux_cmd): an MP4 is only
        playable once FFmpeg closes it, and FFmpeg can't when the Tablo stops sending partway (an
        export on Ubuntu sat at 97% for 47 minutes); a .ts is good up to wherever it stopped."""
        video = (["-c:v", "copy"] if enc is None else
                 ["-vf", "bwdif=mode=send_frame:deint=interlaced", *enc["args"], "-pix_fmt", enc["pix_fmt"]])
        return [
            FFMPEG_PATH,
            "-y",
            "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
            "-fflags", "+discardcorrupt",
            # Capped (see EXPORT_READRATE) unless TabloView paces it (readrate None)
            *(["-readrate", f"{readrate:g}"] if readrate else []),
            "-i", playlist_url,
            *video,
            "-af", "aresample=async=1:ochl=stereo:clev=1.0:slev=0.6",
            "-c:a", "aac", "-b:a", "192k", "-ac", "2",
            "-f", "mpegts",
            str(part_path)
        ]

    @staticmethod
    def remux_cmd(part_path: Path, output_path: Path) -> List[str]:
        """The finished (or salvaged) .ts as the MP4, without converting anything again."""
        return [FFMPEG_PATH, "-y", "-fflags", "+genpts", "-i", str(part_path), "-map", "0:v", "-map", "0:a?",
                "-c", "copy", "-movflags", "+faststart", str(output_path)]

    async def _remux(self, part_path: Path, output_path: Path) -> Optional[str]:
        """Re-package the .ts as the MP4; None if it worked, otherwise why not."""
        def run() -> Optional[str]:
            proc = subprocess.Popen(self.remux_cmd(part_path, output_path), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, creationflags=NO_WINDOW, **childproc.popen_kwargs())
            childproc.tie_to_app(proc)
            _, err = proc.communicate()
            if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return None
            return (err or b"").decode("utf-8", errors="replace")[-400:] or f"FFmpeg exited with code {proc.returncode}"
        return await asyncio.to_thread(run)

    @staticmethod
    def export_seconds(log_tail: str) -> Optional[float]:
        """Seconds of the recording converted so far, from the last "time=HH:MM:SS.xx" FFmpeg wrote."""
        found = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", log_tail)
        if not found:
            return None
        h, m, sec = found[-1]
        return int(h) * 3600 + int(m) * 60 + float(sec)

    @classmethod
    def export_progress(cls, log_tail: str, expected_duration: int) -> Optional[float]:
        """Percent done from the last "time=HH:MM:SS.xx" FFmpeg wrote, or None if unknown."""
        done = cls.export_seconds(log_tail)
        if done is None or not expected_duration:
            return None
        return round(min(99.0, done / expected_duration * 100), 1)

    @staticmethod
    def _stop_stalled_export(proc: subprocess.Popen, done: float, expected_duration: int) -> str:
        """FFmpeg made no progress for EXPORT_STALL_SECONDS: the Tablo stopped sending (FFmpeg waits for
        more and ignores its own quit command while it does). Stop it. Near the end, what arrived is
        kept (the .ts is good up to there); earlier on, say why it stopped."""
        proc.kill()
        proc.wait(timeout=10)
        if expected_duration and done >= expected_duration * EXPORT_NEAR_END:
            return "near_end"
        pct = f" at {round(done / expected_duration * 100)}%" if expected_duration and done > 0 else ""
        return (f"The Tablo stopped sending this recording{pct}, so the export was stopped. "
                f"Try again later; if it stops at the same point, that part of the recording may be damaged.")

    async def _run_ffmpeg_export(self, job_id: str, playlist_url: str, output_path: Path, expected_duration: int,
                                 enc: Optional[Dict[str, Any]] = None, last_try: bool = True) -> bool:
        part_path = output_path.with_name(output_path.stem + ".part.ts")  # becomes the MP4 when done
        from . import export_pace
        relay = export_pace.open_relay(playlist_url)  # TabloView paces it; or directly at EXPORT_READRATE
        cmd = self.export_cmd(relay.url if relay else playlist_url, part_path, enc, None if relay else EXPORT_READRATE)
        print(f"[ExportWorker] Starting export {job_id} -> {output_path.name} "
              f"({enc['label'] if enc else 'original video'})")
        save_export_job({"job_id": job_id, "status": "downloading", "progress": 0.0, "error": None})
        # Send FFmpeg's chatty stderr to a log file instead of an unread pipe,
        # which would fill up and stall long exports
        log_path = TRANSCODE_DIR / f"export_{job_id}.log"
        proc = None
        stalled = None  # why FFmpeg was stopped, if it stopped making progress
        try:
            with open(log_path, "w", encoding="utf-8") as log_f:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f,
                                        creationflags=NO_WINDOW, **childproc.popen_kwargs())
            childproc.tie_to_app(proc)
            self.export_procs[job_id] = proc
            last_done, last_change = -1.0, time.monotonic()

            # Poll progress while process is running
            while proc.poll() is None:
                await asyncio.sleep(2)
                if job_id in self.cancelled_exports:
                    proc.kill()
                    proc.wait(timeout=10)
                    break
                size = part_path.stat().st_size if part_path.exists() else 0
                try:
                    with open(log_path, "rb") as f:
                        f.seek(max(0, log_path.stat().st_size - 4096))
                        tail = f.read().decode("utf-8", errors="replace")
                except OSError:
                    tail = ""
                done = self.export_seconds(tail)
                if done is not None and done > last_done:
                    last_done, last_change = done, time.monotonic()
                elif time.monotonic() - last_change >= EXPORT_STALL_SECONDS:
                    stalled = self._stop_stalled_export(proc, last_done, expected_duration)
                    break
                progress = self.export_progress(tail, expected_duration)
                if progress is None:
                    # Unknown length: a rough guess from the size (about 2 GB per hour)
                    est_bytes = max(expected_duration * 500_000, 10_000_000) if expected_duration else 500_000_000
                    progress = min(round((size / est_bytes) * 90, 1), 95.0)

                save_export_job({
                    "job_id": job_id,
                    "status": "downloading",
                    "progress": progress,
                    "file_size": size
                })

            if job_id in self.cancelled_exports:
                print(f"[ExportWorker] Export {job_id} cancelled")
                save_export_job({"job_id": job_id, "status": "cancelled", "error": None,
                                 "completed_at": datetime.now(timezone.utc).isoformat()})
                return True  # nothing to retry

            try:
                stderr = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                stderr = ""
            if stalled == "near_end":
                print(f"[ExportWorker] Export {job_id}: the Tablo stopped sending near the end "
                      f"({round(last_done)} of {expected_duration} s); keeping what arrived")
            elif stalled:
                # The Tablo's doing, not the encoder's: don't retry on the CPU, just say what happened
                print(f"[ExportWorker] Export {job_id} stalled at {round(last_done)} s; stopped")
                save_export_job({"job_id": job_id, "status": "failed", "error": stalled,
                                 "completed_at": datetime.now(timezone.utc).isoformat()})
                return True
            if (proc.returncode == 0 or stalled == "near_end") and part_path.exists() and part_path.stat().st_size:
                save_export_job({"job_id": job_id, "status": "downloading", "progress": 99.0})
                remux_error = await self._remux(part_path, output_path)
                if remux_error:
                    print(f"[ExportWorker] Export {job_id}: couldn't make the MP4: {remux_error}")
                    output_path.unlink(missing_ok=True)
                    save_export_job({"job_id": job_id, "status": "failed",
                                     "error": f"Couldn't finish the MP4: {remux_error[-200:]}",
                                     "completed_at": datetime.now(timezone.utc).isoformat()})
                    return True
                size = output_path.stat().st_size
                print(f"[ExportWorker] Export {job_id} completed successfully ({round(size / 1024**2, 1)} MB)")
                save_export_job({
                    "job_id": job_id,
                    "status": "completed",
                    "progress": 100.0,
                    "file_size": size,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                })
                return True
            err_msg = stderr[-400:] if stderr else f"FFmpeg exited with code {proc.returncode}"
            print(f"[ExportWorker] Export {job_id} failed: {err_msg}")
            if not last_try:
                return False
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
            export_pace.close_relay(relay)
            self.export_procs.pop(job_id, None)
            self.cancelled_exports.discard(job_id)
            for leftover in (log_path, part_path):  # the .ts is either the MP4 now, or not wanted
                try:
                    leftover.unlink(missing_ok=True)
                except Exception:
                    pass


transcode_manager = TranscodeManager()
