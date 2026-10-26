"""Exports read the recording through TabloView, which hands it to FFmpeg at a pace that suits the
moment: fast while nothing is playing from the Tablo, twice real time as soon as something is (live
TV, a recording, the antenna check, or live TV in another app), and fast again when it stops.

FFmpeg's own -readrate is fixed for the whole export, so it had to be a guess made at the start.
Here the export's playlist is rewritten so every piece comes through /api/export-relay/..., and each
piece of video is held back just long enough to keep to the current pace.

A Tablo recording is one large file, its playlist naming byte ranges in it (#EXT-X-BYTERANGE, about
2.4 seconds each). Each range gets its own name here, and only its bytes are fetched from the Tablo.

Playback of recordings reads through a relay too, unpaced (paced=False): a recording is a chain of
files about 5.5 minutes long, and FFmpeg reading the Tablo's playlist straight from the Tablo lost a
video packet at every join (a 1-2 s glitch every few minutes). The same bytes fetched by TabloView
and handed over piece by piece come out clean (checked on a Tracker recording: 3 damaged packets at
a join read directly, none through TabloView), so the relay hands FFmpeg exactly that."""

import asyncio
import re
import secrets
import time
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from fastapi.responses import Response

FAST_RATE = 5.0  # nothing else playing: a 2-hour recording in about 25 minutes
BUSY_RATE = 2.0  # something playing: leaves the Tablo room for it (unthrottled is about 6.5x)
BURST_SECONDS = 20  # a short head start can go as fast as the Tablo sends
TUNER_CHECK_SECONDS = 15

Piece = Tuple[str, float, Optional[Tuple[int, int]]]  # url, seconds of video, (offset, length) in the file

local_port: Optional[int] = None  # TabloView's own port, learned from the requests it serves
relays: Dict[str, "Relay"] = {}
_tuners: Dict[str, Any] = {"at": 0.0, "busy": False}


def note_port(server: Optional[Tuple[str, int]]) -> None:
    global local_port
    if server and server[1]:
        local_port = server[1]


class Relay:
    """One export's view of a recording: the Tablo's playlists and pieces under short local names."""

    def __init__(self, playlist_url: str, clock: Callable[[], float] = time.monotonic, paced: bool = True):
        self.id = secrets.token_hex(8)
        self.clock = clock
        self.paced = paced
        self.targets: Dict[str, Piece] = {"playlist.m3u8": (playlist_url, 0.0, None)}
        self.names: Dict[Any, str] = {playlist_url: "playlist.m3u8"}  # url, or (url, offset, length)
        self.next_at = clock() - BURST_SECONDS  # the head start

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{local_port}/api/export-relay/{self.id}/playlist.m3u8"

    def _name(self, url: str, prefix: str, seconds: float = 0.0, rng: Optional[Tuple[int, int]] = None) -> str:
        key = (url, *rng) if rng else url
        if key not in self.names:
            ext = (re.search(r"\.[A-Za-z0-9]{1,5}$", urlsplit(url).path) or [""])[0]
            self.names[key] = f"{prefix}{len(self.names)}{ext}"
            self.targets[self.names[key]] = (url, seconds, rng)
        return self.names[key]

    def rewrite(self, text: str, base_url: str) -> str:
        """The playlist with every address pointing back here, each byte range as a piece of its own.
        Lengths come from #EXTINF."""
        out, seconds, variant, rng = [], 0.0, False, None
        ends: Dict[str, int] = {}  # where the last range in each file ended (a range may leave out @offset)
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#EXTINF:"):
                try:
                    seconds = float(s[8:].split(",")[0])
                except ValueError:
                    seconds = 0.0
            if s.startswith("#EXT-X-STREAM-INF"):
                variant = True
            if s.startswith("#EXT-X-BYTERANGE:"):
                length, _, offset = s[17:].partition("@")
                rng = (int(offset) if offset else None, int(length))
                continue  # the piece is a file of its own here
            if s.startswith("#") and 'URI="' in s:
                s = re.sub(r'URI="([^"]+)"', lambda m: f'URI="{self._name(urljoin(base_url, m.group(1)), "a")}"', s)
            elif s and not s.startswith("#"):
                target = urljoin(base_url, s)
                is_playlist = variant or urlsplit(target).path.endswith(".m3u8")
                if rng:
                    offset = rng[0] if rng[0] is not None else ends.get(target, 0)
                    rng = (offset, rng[1])
                    ends[target] = offset + rng[1]
                s = self._name(target, "p" if is_playlist else "s", 0.0 if is_playlist else seconds, rng)
                seconds, variant, rng = 0.0, False, None
            out.append(s)
        return "\n".join(out) + "\n"

    def wait_for(self, seconds: float, rate: float) -> float:
        """How long to hold a piece this many seconds long back, at this pace; then count it."""
        now = self.clock()
        start = max(self.next_at, now - BURST_SECONDS)
        wait = max(0.0, start - now)
        self.next_at = start + seconds / rate
        return wait


def open_relay(playlist_url: str, paced: bool = True) -> Optional[Relay]:
    """A relay for one export (paced) or one recording's playback (not), or None if TabloView's port
    isn't known yet (it then reads directly)."""
    if not local_port:
        return None
    relay = Relay(playlist_url, paced=paced)
    relays[relay.id] = relay
    return relay


def close_relay(relay: Optional[Relay]) -> None:
    if relay:
        relays.pop(relay.id, None)


async def something_playing() -> bool:
    """Anything TabloView is playing from the Tablo, or live TV in another app on the Tablo."""
    from .tablo_client import tablo_manager
    from .transcode import transcode_manager
    if any(not s.stopped for s in transcode_manager.sessions.values()):
        return True
    if time.monotonic() - _tuners["at"] > TUNER_CHECK_SECONDS:
        busy = False
        try:
            resp = await tablo_manager.request_local("GET", "/server/tuners")
            if resp.status_code == 200:
                # Watching (a channel, not a recording); recordings in progress don't need the room
                busy = any(t.get("in_use") and t.get("channel") and not t.get("recording") for t in resp.json())
        except Exception:
            pass
        _tuners.update(at=time.monotonic(), busy=busy)
    return _tuners["busy"]


async def serve(relay_id: str, name: str) -> Response:
    from .transcode import transcode_manager
    relay = relays.get(relay_id)
    target = relay and relay.targets.get(name)
    if not target:
        return Response("Not found", status_code=404)
    url, seconds, rng = target
    if seconds and relay.paced:
        rate = BUSY_RATE if await something_playing() else FAST_RATE
        wait = relay.wait_for(seconds, rate)
        if wait:
            await asyncio.sleep(wait)
    headers = {"Range": f"bytes={rng[0]}-{rng[0] + rng[1] - 1}"} if rng else None
    resp = await transcode_manager._http.get(url, headers=headers, timeout=30)
    if resp.status_code not in (200, 206):
        return Response(resp.content, status_code=resp.status_code)
    if name.endswith(".m3u8"):
        return Response(relay.rewrite(resp.text, url), media_type="application/vnd.apple.mpegurl")
    return Response(resp.content, media_type=resp.headers.get("content-type") or "video/mp2t")
