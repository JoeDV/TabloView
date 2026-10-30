"""Commercial breaks found by Claude, for anyone who adds their own Anthropic API key (Settings → Playback).

The Tablo's own preview pictures (one about every 10 seconds, app/previews.py) are laid out on contact
sheets labelled with their times and sent to Claude, which says where the breaks are. Its edges are then
moved onto the black frames the commercial finder measured (app/commercials.py), which are exact to a
fraction of a second; an edge with no black frame nearby moves EDGE_INWARD seconds into the break, so a
few seconds of ad are left rather than any of the show.

Checked on eight recordings with their real breaks marked (2026-10-30): 93-100% of the ad time skipped
and 25 s of show skipped across all eight, where the finder alone skipped 654 s of show (627 s of it in
Survivor, whose firelit Tribal Council it took for ads) and left a fifth of The Price Is Right's ads in.
Without a key, or if Claude can't be reached, the finder's own breaks are used as before.
"""

import base64
import io
import json
from typing import Dict, List, Optional

from . import previews
from .settings import load_settings

MODEL = "claude-opus-5-5"
SHEET_COLS, SHEET_ROWS = 12, 8  # 96 pictures a sheet: an hour of TV is four sheets
THUMB_W, THUMB_H, LABEL_H = 160, 90, 14
EDGE_WINDOW = 10  # look this far either side of Claude's edge for a black frame (its pictures are ~10 s apart)
EDGE_INWARD = 5  # no black frame there: move the edge this far into the break
MIN_BREAK = 10  # shorter than this isn't a break

PROMPT = """You are looking at a US network over-the-air TV recording: {what}, about {minutes} minutes long. \
The images are contact sheets of preview frames from it, in order, one frame roughly every 10 seconds, each \
labelled in yellow with its time in minutes:seconds from the start of the recording.

Task: Identify every commercial break: every stretch that is not the program itself. This includes:
- Paid ads
- Network promos for other shows
- Station IDs / station breaks
- The end of whatever aired before the program, at the start of the recording
- Anything after the program's end credits

Do NOT mark as a break:
- The program's own content
- Opening titles / cold open
- Recaps
- "Next time on..." or "Previously on..." segments that belong to this program
- End credits of this program
- The program's own title cards and logo bumpers going into or coming out of a break

How to decide (use these cues, in order of strength):
1. Channel logo (bug) is usually present during the show and absent (or different) during ads/promos.
2. Abrupt style change: different color grading, graphics package, product shots, voiceover text, \
lower-thirds, or lower production value.
3. Black or near-black frames, or solid-color slates, often appear at the edges of breaks.
4. Rapid visual change / many different scenes in a short time (typical of ads).
5. Network or station branding that is not part of the show's own graphics.

Because frames are ~10 seconds apart, the true edge lies between the last program frame and the first ad \
frame. For each boundary, give the midpoint between those two labelled times, in seconds from the start of \
the recording. A break that runs to the end of the recording ends at {seconds}."""

SCHEMA = {
    "type": "object",
    "properties": {
        "breaks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"start_seconds": {"type": "number"}, "end_seconds": {"type": "number"}},
                "required": ["start_seconds", "end_seconds"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["breaks"],
    "additionalProperties": False,
}


def api_key() -> Optional[str]:
    return (load_settings().get("claude_api_key") or "").strip() or None


def sheets(episode_id: str) -> List[bytes]:
    """The recording's previews as JPEG contact sheets, each picture labelled with its time."""
    from PIL import Image, ImageDraw
    times = previews.times(episode_id) or []
    per = SHEET_COLS * SHEET_ROWS
    out = []
    for first in range(0, len(times), per):
        n = min(per, len(times) - first)
        rows = (n + SHEET_COLS - 1) // SHEET_COLS
        sheet = Image.new("RGB", (SHEET_COLS * THUMB_W, rows * (THUMB_H + LABEL_H)), "black")
        draw = ImageDraw.Draw(sheet)
        for i in range(n):
            data = previews.frame(episode_id, first + i)
            x, y = (i % SHEET_COLS) * THUMB_W, (i // SHEET_COLS) * (THUMB_H + LABEL_H)
            if data:
                try:
                    sheet.paste(Image.open(io.BytesIO(data)).convert("RGB").resize((THUMB_W, THUMB_H)), (x, y + LABEL_H))
                except OSError:
                    pass  # a damaged picture stays black
            t = int(times[first + i])
            draw.text((x + 3, y + 1), f"{t // 60}:{t % 60:02d}", fill="yellow")
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=80)
        out.append(buf.getvalue())
    return out


def ask(key: str, images: List[bytes], what: str, seconds: float) -> List[List[float]]:
    """Claude's breaks as [[start, end], ...]. Raises on any failure (no key, network, refusal)."""
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=300)
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.standard_b64encode(img).decode()}} for img in images]
    content.append({"type": "text", "text": PROMPT.format(what=what, minutes=round(seconds / 60), seconds=round(seconds))})
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # a declined request is retried on Anthropic's recommended model
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off")
    text = next(b.text for b in response.content if b.type == "text")
    return [[float(b["start_seconds"]), float(b["end_seconds"])] for b in json.loads(text)["breaks"]]


def onto_black_frames(found: List[List[float]], blacks: List[float], n: float) -> List[Dict[str, float]]:
    """Each edge onto a black frame within EDGE_WINDOW (of those, the one making the break shorter),
    else EDGE_INWARD into the break. Edges at the very start or end of the recording stay there."""
    out = []
    for start, end in sorted(found):
        near_start = [b for b in blacks if abs(b - start) <= EDGE_WINDOW]
        near_end = [b for b in blacks if abs(b - end) <= EDGE_WINDOW]
        s = 0.0 if start <= 1 else max(near_start) if near_start else start + EDGE_INWARD
        e = float(n) if end >= n - 5 else min(near_end) if near_end else end - EDGE_INWARD
        if e - s >= MIN_BREAK:
            out.append({"start": round(s, 1), "end": round(e, 1)})
    return out


def find(ep: Dict[str, str], blacks: List[float], n: float) -> Optional[List[Dict[str, float]]]:
    """The breaks per Claude, on the finder's black frames, or None to keep the finder's own (no key,
    no previews, or Claude couldn't be asked). Blocking: run it in a thread."""
    key = api_key()
    if not key:
        return None
    images = sheets(ep["id"])
    if not images:
        print(f"[Commercials] No preview pictures for {ep['title']}, so Claude wasn't asked")
        return None
    try:
        found = ask(key, images, ep["title"], n)
    except Exception as e:
        print(f"[Commercials] Claude couldn't find the breaks in {ep['title']}: {e}")
        status["error"] = str(e)[:300]
        return None
    status["error"] = None
    return onto_black_frames(found, blacks, n)


status: Dict[str, Optional[str]] = {"error": None}  # the last call's failure, for Settings


def check_key(key: str) -> Optional[str]:
    """Why this key can't be used, or None if Anthropic accepts it (a free call: no tokens used)."""
    import anthropic
    try:
        anthropic.Anthropic(api_key=key, timeout=20, max_retries=1).models.retrieve(MODEL)
        return None
    except anthropic.AuthenticationError:
        return "Anthropic didn't accept that key"
    except anthropic.PermissionDeniedError:
        return f"That key can't use {MODEL}"
    except anthropic.APIConnectionError:
        return "Couldn't reach Anthropic: check the internet connection"
    except anthropic.APIStatusError as e:
        return f"Anthropic answered with an error ({e.status_code})"
