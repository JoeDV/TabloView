"""Timeline preview frames from the Tablo's own trick-play file.

The watch response for a recording includes bif_url_hd: a Roku BIF file with a small JPEG (320x180)
about every 10 seconds of the whole recording, about 2 MB for half an hour, fetched in one request.
It's cached per episode in data/previews (re-fetched while a recording is still in progress) and
served frame by frame for the timeline's hover preview.

BIF layout: magic (8 bytes), version, frame count, timestamp multiplier in ms (uint32 LE each),
then from byte 64 an index of (timestamp, offset) pairs ending with an 0xffffffff entry, then the
JPEGs back to back.
"""

import json
import struct
import time
from typing import List, Optional

import httpx

from .config import DATA_DIR

MAGIC = b"\x89BIF\r\n\x1a\n"
CACHE_DIR = DATA_DIR / "previews"
KEEP_DAYS = 30


def parse(data: bytes) -> List[List[float]]:
    """[[seconds, start offset, end offset], ...] for each frame. ValueError if it isn't a BIF file."""
    if data[:8] != MAGIC or len(data) < 72:
        raise ValueError("not a BIF file")
    _version, count, mult = struct.unpack("<III", data[8:20])
    mult = mult or 1000
    index = [struct.unpack("<II", data[64 + 8 * i:72 + 8 * i]) for i in range(count + 1)]
    return [[round(ts * mult / 1000, 2), start, end]
            for (ts, start), (_, end) in zip(index, index[1:]) if 0 < start < end <= len(data)]


def _paths(episode_id: str):
    safe = "".join(c for c in episode_id if c.isalnum() or c in "_-")
    return CACHE_DIR / f"{safe}.bif", CACHE_DIR / f"{safe}.json"


def times(episode_id: str) -> Optional[List[float]]:
    """Frame times in seconds, if this episode's previews are here."""
    _, index = _paths(episode_id)
    try:
        return [f[0] for f in json.loads(index.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        return None


def frame(episode_id: str, n: int) -> Optional[bytes]:
    bif, index = _paths(episode_id)
    try:
        frames = json.loads(index.read_text(encoding="utf-8"))
        _, start, end = frames[n]
        with open(bif, "rb") as f:
            f.seek(start)
            return f.read(end - start)
    except (OSError, ValueError, IndexError):
        return None


async def fetch(episode_id: str, bif_url: str, finished: bool) -> None:
    """Download and index the previews unless a finished recording's are already cached. Never raises."""
    bif, index = _paths(episode_id)
    if finished and index.exists():
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(bif_url)
        if r.status_code != 200:
            print(f"[Previews] The Tablo's preview file wasn't available (HTTP {r.status_code})")
            return
        frames = parse(r.content)
        bif.write_bytes(r.content)
        index.write_text(json.dumps(frames), encoding="utf-8")
        _prune()
    except Exception as e:
        print(f"[Previews] Couldn't get the preview frames: {e}")


def _prune() -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    for p in CACHE_DIR.glob("*"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
