"""Live TV routing: channel lineup, tuner status, and real-time live streaming."""

import re
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

import httpx
import requests
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from ..tablo_client import tablo_manager
from ..transcode import transcode_manager
from ..database import get_live_airings_for_channels, get_epg_schedule, get_upcoming_recordings
from ..schedule_check import live_tv_check
from ..settings import load_settings
from tablo_api import TabloClient, TabloAuth
import tablo_api.client as tc

router = APIRouter(prefix="/api/live", tags=["Live TV"])

# In-memory cache for cloud FAST channel schedule grid (15-minute TTL)
_cloud_grid_cache: Dict[str, Any] = {
    "timestamp": 0,
    "day": "",
    "grid_by_identifier": {},
    "channel_info_by_identifier": {}
}


async def get_cached_cloud_grid(day_str: str) -> Dict[str, Any]:
    """Retrieve full 108-channel cloud grid from Scripps Lighthouse, cached in memory."""
    global _cloud_grid_cache
    now = time.time()
    if (
        _cloud_grid_cache["grid_by_identifier"]
        and _cloud_grid_cache["day"] == day_str
        and (now - _cloud_grid_cache["timestamp"]) < 900
    ):
        return _cloud_grid_cache

    dev = tablo_manager.device
    if not dev or not dev.lighthouse_token:
        return _cloud_grid_cache

    url = f"{tc._CLOUD_HOST}/api/v2/account/{dev.lighthouse_token}/guide/grid/?day={day_str}&limit=200"
    headers = {
        "Authorization": f"Bearer {dev.account_token}",
        "Lighthouse": dev.lighthouse_token,
        "User-Agent": tc._CLOUD_USER_AGENT
    }

    try:
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=15))
        if r.status_code in (401, 403):
            tablo_manager.note_auth("cloud", ok=False)
        if r.status_code == 200:
            tablo_manager.note_auth("cloud", ok=True)
            grid_list = r.json().get("grid", [])
            by_ident: Dict[str, List[Dict[str, Any]]] = {}
            ch_info: Dict[str, Dict[str, Any]] = {}
            for item in grid_list:
                ch = item.get("channel", {})
                ident = ch.get("identifier")
                if ident:
                    by_ident[ident] = item.get("airings", [])
                    ch_info[ident] = ch
            _cloud_grid_cache = {
                "timestamp": now,
                "day": day_str,
                "grid_by_identifier": by_ident,
                "channel_info_by_identifier": ch_info
            }
            print(f"[LiveTV] Successfully cached cloud grid for {day_str} ({len(by_ident)} channels)")
    except Exception as e:
        print(f"[LiveTV] Error fetching cloud grid: {e}")

    return _cloud_grid_cache


async def fetch_local_ota_map() -> Dict[str, Dict[str, Any]]:
    """Fetch OTA channel details (logos, resolution) from the local device, 50 channels per request
    (tablo_manager.batch_get). If the Tablo rejects a batch, those channels show without their local
    details rather than the page waiting."""
    local_ota_map: Dict[str, Dict[str, Any]] = {}
    try:
        resp = await tablo_manager.request_local("GET", "/guide/channels")
        if resp.status_code != 200:
            return local_ota_map

        for p, c_data in (await tablo_manager.batch_get(resp.json())).items():
            # Keep the device path (e.g. /guide/channels/17182): tuners report busy channels by path
            c_info = {**c_data.get("channel", {}), "_path": p}
            ident = c_info.get("channel_identifier") or str(c_data.get("object_id"))
            local_ota_map[ident] = c_info
    except Exception as e:
        print(f"[LiveTV] Notice fetching local channels: {e}")
    return local_ota_map


async def fetch_cloud_channels(client: TabloClient, include_ott: bool) -> list:
    """Fetch the cloud channel lineup (OTA + FAST). TabloClient is synchronous, so run it in a thread."""
    try:
        channels = await asyncio.to_thread(client.channels, include_ott=include_ott)
        tablo_manager.note_auth("cloud", ok=True)
        return channels
    except Exception as e:
        if re.search(r"\b40[13]\b", str(e)):
            tablo_manager.note_auth("cloud", ok=False)
        print(f"[LiveTV] Error fetching cloud channels: {e}")
        return []


async def recording_channel_identifiers(local_ota_map: Dict[str, Dict[str, Any]]) -> set:
    """Channel identifiers the Tablo is recording from right now (read live from its tuners)."""
    try:
        resp = await tablo_manager.request_local("GET", "/server/tuners")
        if resp.status_code != 200:
            return set()
        busy_paths = {t.get("channel") for t in resp.json() if t.get("in_use") and t.get("recording") and t.get("channel")}
    except Exception as e:
        print(f"[LiveTV] Couldn't read tuners for recording badges: {e}")
        return set()
    return {ident for ident, info in local_ota_map.items() if info.get("_path") in busy_paths}


def mark_recording_now(airings: List[Dict[str, Any]], now_utc: datetime):
    """Flag the airing on air right now on a channel that a tuner is recording."""
    for a in airings:
        try:
            start = datetime.fromisoformat(str(a["air_datetime"]).replace("Z", "+00:00"))
            if start <= now_utc < start + timedelta(seconds=a.get("duration") or 0):
                a["recording_now"] = True
        except (KeyError, ValueError, TypeError):
            continue


_NEWS_GENRES = {"news", "newsmagazine", "weather", "public affairs", "politics"}
_SPORTS_GENRES = {"sports", "sports event", "sports talk", "sports non-event", "football", "basketball",
                  "baseball", "hockey", "soccer", "golf", "auto racing", "boxing", "wrestling", "tennis"}


def channel_categories(c: Dict[str, Any]) -> List[str]:
    """Live TV categories from what a channel airs in the window (genre share by airtime), so they
    work in any market. A channel is News/Sports when at least 40% of its airtime is that genre;
    channels that aren't mostly news or sports count as Entertainment."""
    totals = {"news": 0.0, "sports": 0.0}
    total = 0.0
    for a in c.get("airings") or []:
        dur = float(a.get("duration") or 0)
        genres = {str(g).lower() for g in (a.get("genres") or [])}
        if (a.get("category") or "").lower() == "sports":
            genres.add("sports")
        total += dur
        if genres & _NEWS_GENRES:
            totals["news"] += dur
        if genres & _SPORTS_GENRES:
            totals["sports"] += dur
    name = (c.get("name") or "").lower()
    cats = [k for k, v in totals.items() if total and v / total >= 0.4]
    # Channel names are a reliable hint for single-topic streaming channels
    if "news" not in cats and any(w in name for w in ("news", "weather")):
        cats.append("news")
    if "sports" not in cats and "sport" in name:
        cats.append("sports")
    if not cats:
        cats.append("entertainment")
    return cats


_LOGO_ORDER = {
    # "originalLarge" is the station's own colors (NBC's peacock, Univision's U); some are white anyway
    "color": ("originalLarge", "lightLarge", "darkLarge"),
    "white": ("lightLarge", "originalLarge", "darkLarge"),  # "darkLarge" is the black version
}
_logo_style_cache: Dict[str, Any] = {"at": 0.0, "style": "color"}


def logo_style() -> str:
    """Device > Playback > Channel logos, read at most every few seconds (it's asked once per channel)."""
    if time.time() - _logo_style_cache["at"] > 5:
        _logo_style_cache.update(at=time.time(), style=load_settings().get("logo_style") or "color")
    return _logo_style_cache["style"]


def pick_logo(logos: List[Dict[str, Any]], style: Optional[str] = None) -> Optional[str]:
    """The channel logo in the chosen style: the station's colors (default) or all white."""
    by_kind = {lg.get("kind"): lg.get("url") for lg in logos or [] if lg.get("url")}
    for kind in _LOGO_ORDER.get(style or logo_style(), _LOGO_ORDER["color"]):
        if by_kind.get(kind):
            return by_kind[kind]
    return None


def base_channel_dict(ch, cloud_ch_info: Dict[str, Any], local_ota_map: Dict[str, Any]) -> Dict[str, Any]:
    """Common channel fields shared by /channels and /epg, with logo and resolution resolved."""
    c_cloud = cloud_ch_info.get(ch.identifier, {})
    clean_name = c_cloud.get("name") or (f"{ch.major}.{ch.minor} {ch.call_sign}" if ch.major > 0 else ch.call_sign)

    c_dict: Dict[str, Any] = {
        "channel_id": ch.identifier,
        "identifier": ch.identifier,
        "call_sign": ch.call_sign,
        "major": ch.major,
        "minor": ch.minor,
        "network": ch.network or "",
        "kind": "ota" if ch.kind == "ota" else "fast",
        "name": clean_name,
        "logo_url": None,
        "resolution": "HD",
        "favorite": False,
    }

    # Local OTA enriched info (logos, resolution, favorites set in Tablo's apps)
    if ch.identifier in local_ota_map:
        loc = local_ota_map[ch.identifier]
        c_dict["favorite"] = bool(loc.get("favourite"))
        c_dict["resolution"] = loc.get("resolution", "HD").upper().replace("HD_", "") + "p" if loc.get("resolution") else "HD"
        c_dict["logo_url"] = pick_logo(loc.get("logos", []))

    # Cloud logos (for FAST channels)
    if not c_dict["logo_url"]:
        c_dict["logo_url"] = pick_logo(c_cloud.get("logos", []))

    return c_dict


class TuneRequest(BaseModel):
    channel_id: str
    transcode: bool = True
    kind: Optional[str] = None  # 'ota' or 'fast', from the channel list


class StopRequest(BaseModel):
    session_id: str


_model_tuner_count: Dict[str, int] = {}


async def model_tuner_count() -> Optional[int]:
    """Antenna tuners per the device model (e.g. 4 for a QUAD), cached per device.
    /server/tuners lists twice that on a 4G QUAD: the first N slots are the antenna (OTA) tuners,
    the rest are virtual slots used by streaming (FAST) channels (verified by tuning one of each)."""
    sid = tablo_manager.device.sid
    if sid not in _model_tuner_count:
        try:
            resp = await tablo_manager.request_local("GET", "/server/info")
            count = (resp.json().get("model") or {}).get("tuners") if resp.status_code == 200 else None
            if isinstance(count, int) and count > 0:
                _model_tuner_count[sid] = count
        except Exception as e:
            print(f"[LiveTV] Could not read model tuner count: {e}")
    return _model_tuner_count.get(sid)


@router.get("/tuners")
async def get_tuner_status():
    """Check hardware tuner occupancy on the Tablo DVR."""
    if not tablo_manager.is_authenticated:
        return {"tuners": [], "total": 0, "in_use": 0}

    try:
        resp = await tablo_manager.request_local("GET", "/server/tuners")
        if resp.status_code == 200:
            tuners = resp.json()
            total = await model_tuner_count() or len(tuners)
            ota = tuners[:total]
            in_use = sum(1 for t in ota if t.get("in_use"))
            # A closed live stream keeps its tuner busy for a while with no channel attached;
            # the Tablo releases it on its own (we found no way to release it sooner)
            held = sum(1 for t in ota if t.get("in_use") and not t.get("channel") and not t.get("recording"))
            recording = sum(1 for t in ota if t.get("in_use") and t.get("recording"))
            streams_in_use = sum(1 for t in tuners[total:] if t.get("in_use"))
            return {
                "tuners": tuners,
                "total": total,
                "in_use": in_use,
                "held": held,
                "recording": recording,
                "available": total - in_use,
                "streams_in_use": streams_in_use,
                "streams_total": max(len(tuners) - total, 0),
            }
    except Exception as e:
        print(f"[LiveTV] Error reading tuners: {e}")

    return {"tuners": [], "total": 0, "in_use": 0, "available": 0, "streams_in_use": 0, "streams_total": 0,
            "unreachable": tablo_manager.tablo_unreachable}


@router.get("/channels")
async def get_live_channels(kind: str = Query("all", description="all, ota, fast")):
    """Return live channels enriched with network logos and currently airing program."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device not connected")

    dev = tablo_manager.device
    client = TabloClient(dev)

    # 1. Fetch live channels from cloud and local device
    channels_result: List[Dict[str, Any]] = []

    # Map for matching call signs with current guide airings
    guide_now = get_live_airings_for_channels()

    # Pre-fetch cloud grid for FAST logos and current airings
    now_utc = datetime.now(timezone.utc)
    day_str = now_utc.strftime("%Y-%m-%d")
    cloud_cache = await get_cached_cloud_grid(day_str)
    cloud_grid_by_id = cloud_cache.get("grid_by_identifier", {})
    cloud_ch_info = cloud_cache.get("channel_info_by_identifier", {})

    # Fetch local OTA channel details and the full cloud lineup (OTA + FAST) concurrently
    include_ott = kind in ("all", "fast")
    local_ota_map, raw_channels = await asyncio.gather(
        fetch_local_ota_map(),
        fetch_cloud_channels(client, include_ott)
    )

    for ch in raw_channels:
        if kind == "ota" and ch.kind != "ota":
            continue
        if kind == "fast" and ch.kind != "ott":
            continue

        c_dict = base_channel_dict(ch, cloud_ch_info, local_ota_map)
        c_dict["now_playing"] = None
        c_dict["next_up"] = None

        # Match "now playing" and "next up" from guide airings
        call_sign_clean = ch.call_sign.upper().replace("-HD", "").replace("DT1", "").strip()
        matched_guide = guide_now.get(ch.call_sign) or guide_now.get(call_sign_clean)

        if matched_guide:
            c_dict["now_playing"] = matched_guide.get("now")
            c_dict["next_up"] = matched_guide.get("next")
        elif ch.identifier in cloud_grid_by_id:
            # Match current & next from cloud airings
            c_airings = cloud_grid_by_id[ch.identifier]
            for idx, a in enumerate(c_airings):
                try:
                    a_start = datetime.fromisoformat(a["datetime"].replace("Z", "+00:00"))
                    a_end = a_start + timedelta(seconds=a["duration"])
                    if a_start <= now_utc < a_end:
                        elapsed = (now_utc - a_start).total_seconds()
                        dur = max(a["duration"], 60)
                        pct = min(max(int((elapsed / dur) * 100), 0), 100)
                        show_title = (a.get("show") or {}).get("title") or a.get("title") or c_dict["name"]
                        ep_title = a.get("title") if (a.get("show") and a.get("show", {}).get("title") != a.get("title")) else ""
                        c_dict["now_playing"] = {
                            "title": show_title,
                            "show_title": show_title,
                            "episode_title": ep_title,
                            "air_date_time": a.get("datetime"),
                            "air_datetime": a.get("datetime"),
                            "duration": a.get("duration"),
                            "progress_pct": pct,
                        }
                        if idx + 1 < len(c_airings):
                            next_a = c_airings[idx + 1]
                            next_show = (next_a.get("show") or {}).get("title") or next_a.get("title") or c_dict["name"]
                            c_dict["next_up"] = {
                                "title": next_show,
                                "show_title": next_show,
                                "episode_title": next_a.get("title") if (next_a.get("show") and next_a.get("show", {}).get("title") != next_a.get("title")) else "",
                                "air_date_time": next_a.get("datetime"),
                                "air_datetime": next_a.get("datetime"),
                                "duration": next_a.get("duration")
                            }
                        break
                except Exception:
                    pass

        channels_result.append(c_dict)

    # Sort OTA channels by channel number, FAST channels alphabetically
    def sort_key(c):
        if c["kind"] == "ota":
            return (0, c["major"], c["minor"])
        return (1, 0, c["call_sign"])

    channels_result.sort(key=sort_key)

    return {
        "count": len(channels_result),
        "channels": channels_result
    }


@router.get("/tune_check")
async def tune_check():
    """Before tuning an antenna channel: would it leave too few tuners for recordings starting soon?"""
    status = await get_tuner_status()
    return live_tv_check(get_upcoming_recordings(within_hours=2), status.get("total", 0),
                         status.get("in_use", 0), status.get("held", 0))


@router.get("/epg")
async def get_live_epg(
    hours: int = Query(6, ge=1, le=24),
    start_iso: Optional[str] = Query(None),
    kind: str = Query("all", description="all, ota, fast")
):
    """Return live EPG grid schedule with channels and timeline airings."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device not connected")

    dev = tablo_manager.device
    client = TabloClient(dev)

    # 1. Fetch OTA airings in window from local SQLite
    epg_data = get_epg_schedule(hours=hours, start_iso=start_iso)
    by_channel = epg_data["airings_by_channel"]
    by_identifier = epg_data.get("airings_by_identifier", {})

    window_start_dt = datetime.fromisoformat(epg_data["window_start"].replace("Z", "+00:00"))
    window_end_dt = datetime.fromisoformat(epg_data["window_end"].replace("Z", "+00:00"))
    day_str = window_start_dt.strftime("%Y-%m-%d")

    # 2. Fetch/cache cloud FAST channel schedule grid from Scripps Lighthouse
    cloud_cache = await get_cached_cloud_grid(day_str)
    cloud_grid_by_id = cloud_cache.get("grid_by_identifier", {})
    cloud_ch_info = cloud_cache.get("channel_info_by_identifier", {})

    # 3 & 4. Local OTA channel details and cloud channel lineup, fetched concurrently
    include_ott = kind in ("all", "fast")
    local_ota_map, raw_channels = await asyncio.gather(
        fetch_local_ota_map(),
        fetch_cloud_channels(client, include_ott)
    )

    recording_now = await recording_channel_identifiers(local_ota_map)
    now_utc = datetime.now(timezone.utc)

    channel_rows: List[Dict[str, Any]] = []
    for ch in raw_channels:
        if kind == "ota" and ch.kind != "ota":
            continue
        if kind == "fast" and ch.kind != "ott":
            continue

        c_dict = base_channel_dict(ch, cloud_ch_info, local_ota_map)
        c_dict["airings"] = []

        # Match airings by the channel's stable identifier; fall back to call-sign variants for
        # guide data synced before identifiers were stored
        clean_cs = ch.call_sign.upper().replace("-HD", "").replace("DT1", "").strip()
        matched_airings = (by_identifier.get(ch.identifier) or by_channel.get(ch.call_sign)
                           or by_channel.get(clean_cs) or by_channel.get(f"{clean_cs}-1"))

        if matched_airings:
            c_dict["airings"] = matched_airings
            if ch.identifier in recording_now:
                c_dict["recording_now"] = True
                mark_recording_now(matched_airings, now_utc)
        elif ch.identifier in cloud_grid_by_id:
            # Extract FAST channel airings from cloud grid that overlap the window
            cloud_airings: List[Dict[str, Any]] = []
            for a in cloud_grid_by_id[ch.identifier]:
                try:
                    a_start = datetime.fromisoformat(a["datetime"].replace("Z", "+00:00"))
                    a_end = a_start + timedelta(seconds=a["duration"])
                    if a_end > window_start_dt and a_start < window_end_dt:
                        show_title = (a.get("show") or {}).get("title") or a.get("title") or c_dict["name"]
                        ep_title = a.get("title") if (a.get("show") and a.get("show", {}).get("title") != a.get("title")) else ""
                        ep_info = a.get("episode") or {}
                        season_num = (ep_info.get("season") or {}).get("number") if isinstance(ep_info.get("season"), dict) else ep_info.get("season")
                        ep_num = ep_info.get("episodeNumber")

                        poster_url = None
                        for img in a.get("images", []):
                            if img.get("kind") in ("poster", "coverLarge", "coverSmall"):
                                poster_url = img.get("url")
                                break

                        cloud_airings.append({
                            "path": f"/cloud/airing/{a.get('identifier')}",
                            "series_path": None,
                            "title": show_title,
                            "show_title": show_title,
                            "episode_title": ep_title,
                            "description": a.get("description", ""),
                            "season_number": season_num,
                            "episode_number": ep_num,
                            "air_datetime": a.get("datetime"),
                            "duration": a.get("duration", 1800),
                            "is_new": "new" in (a.get("qualifierTags") or []),
                            "is_primetime": False,
                            "is_premiere": "premiere" in (a.get("qualifierTags") or []),
                            "qualifiers": a.get("qualifierTags", []),
                            "genres": a.get("genres") or [],
                            "category": (a.get("show") or {}).get("category") or "",
                            "cover_url": poster_url
                        })
                except Exception:
                    pass

            if cloud_airings:
                c_dict["airings"] = cloud_airings
            else:
                c_dict["airings"] = [
                    {
                        "path": f"/channel/{ch.identifier}/live",
                        "series_path": None,
                        "title": c_dict["name"],
                        "show_title": c_dict["name"],
                        "episode_title": "Live 24/7 Broadcast",
                        "season_number": None,
                        "episode_number": None,
                        "air_datetime": epg_data["window_start"],
                        "duration": hours * 3600,
                        "is_new": False,
                        "is_primetime": False,
                        "is_premiere": False,
                        "qualifiers": []
                    }
                ]
        else:
            c_dict["airings"] = [
                {
                    "path": f"/channel/{ch.identifier}/live",
                    "series_path": None,
                    "title": c_dict["name"],
                    "show_title": c_dict["name"],
                    "episode_title": "Live 24/7 Broadcast",
                    "season_number": None,
                    "episode_number": None,
                    "air_datetime": epg_data["window_start"],
                    "duration": hours * 3600,
                    "is_new": False,
                    "is_primetime": False,
                    "is_premiere": False,
                    "qualifiers": []
                }
            ]

        c_dict["categories"] = channel_categories(c_dict)
        channel_rows.append(c_dict)

    def sort_key(c):
        if c["kind"] == "ota":
            return (0, c["major"], c["minor"])
        return (1, 0, c["call_sign"])

    channel_rows.sort(key=sort_key)

    return {
        "window_start": epg_data["window_start"],
        "window_end": epg_data["window_end"],
        "hours": epg_data["hours"],
        "slots": epg_data["slots"],
        "count": len(channel_rows),
        "channels": channel_rows
    }


@router.post("/tune")
async def tune_live_channel(req: TuneRequest):
    """Tune a live OTA or FAST channel on the Tablo DVR and return streaming URL."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device not connected")

    dev = tablo_manager.device
    client = TabloClient(dev)

    channel_id = req.channel_id
    # Changing channels: let the Tablo hear that the old one ended before asking for a tuner,
    # otherwise a 2-tuner Tablo can briefly count both and refuse the new one
    await transcode_manager.wait_for_ended_sessions()
    try:
        # Tune via TabloClient (synchronous, so keep it off the event loop)
        stream = await asyncio.to_thread(client.watch, channel_id)
        if not stream or not stream.playlist_url:
            raise ValueError("No playlist URL returned by Tablo")

        if req.transcode:
            # Streaming channels usually arrive as H.264 already: pass the video through untouched
            # (sharper, less CPU). Antenna channels are MPEG-2 and always need converting.
            passthrough = req.kind == "fast" and (await transcode_manager.probe_video_codec(stream.playlist_url)) == "h264"
            sess = transcode_manager.create_session(stream.playlist_url)
            sess.tablo_token = stream.token
            stream_url = await transcode_manager.start_browser_transcode(sess.session_id, stream.playlist_url,
                                                                         passthrough=passthrough)
            if req.kind != "fast":
                transcode_manager.start_reception(sess)  # streaming channels have no antenna signal
            return {
                "session_id": sess.session_id,
                "stream_url": stream_url,
                "channel_id": channel_id,
                "token": stream.token,
                "expires": stream.expires,
                "keepalive": stream.keepalive
            }
        else:
            return {
                "session_id": None,
                "stream_url": stream.playlist_url,
                "channel_id": channel_id,
                "token": stream.token
            }
    except Exception as e:
        if re.search(r"\b401\b", str(e)):
            tablo_manager.note_auth("device", ok=False)
        print(f"[LiveTV] Error tuning channel {channel_id}: {e}")
        # TabloClient uses requests; a refused or timed-out connection means the Tablo isn't answering
        if isinstance(e, (httpx.TransportError, requests.ConnectionError, requests.Timeout)):
            if tablo_manager.unreachable_since is None:
                tablo_manager.unreachable_since = time.time()
            raise HTTPException(status_code=503, detail=tablo_manager.UNREACHABLE_MESSAGE)
        busy = await all_tuners_busy_message() if req.kind != "fast" else None
        if busy:
            raise HTTPException(status_code=409, detail=busy)
        if req.kind != "fast" and _refused(e):
            raise HTTPException(status_code=502, detail=NO_PICKUP_MESSAGE)
        raise HTTPException(status_code=500, detail=f"Failed to tune live channel: {e}")


# The Tablo answers 503 to a watch request both when it has no tuner free and when it can't pick up
# the station (69.1 WDTI, 2026-10-20: refused with a tuner free that tuned 6.1 straight after). Once
# all_tuners_busy_message has ruled out the first, it's the second.
NO_PICKUP_MESSAGE = ("The Tablo can't pick up this channel right now: a tuner is free, but it couldn't tune the "
                     "station. The signal may be too weak where your antenna is pointed, or the station may be "
                     "off the air. The Antenna helper can check your other channels.")


def _refused(e: Exception) -> bool:
    resp = getattr(e, "response", None)
    return isinstance(e, requests.HTTPError) and resp is not None and resp.status_code == 503


async def all_tuners_busy_message() -> Optional[str]:
    """After a refused tune: if every antenna tuner is busy, say why in plain words (None otherwise)."""
    status = await get_tuner_status()
    total = status.get("total") or 0
    if not total or status.get("available", 1) > 0:
        return None
    held, recording = status.get("held") or 0, status.get("recording") or 0
    reasons = []
    if recording:
        reasons.append(f"{recording} recording")
    if held:
        reasons.append(f"{held} still held by the Tablo from live TV you closed (it frees "
                       f"{'that one' if held == 1 else 'those'} on its own, usually within 10–45 minutes)")
    others = total - held - recording
    if others > 0:
        reasons.append(f"{others} watching live TV")
    return f"All {total} antenna tuners are busy: {', '.join(reasons)}. Recordings still play."


@router.get("/vlc/{channel_id}")
async def get_live_vlc_playlist(channel_id: str):
    """Generate instant .m3u playlist file to stream live channel natively in VLC."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device not connected")

    dev = tablo_manager.device
    client = TabloClient(dev)

    try:
        stream = await asyncio.to_thread(client.watch, channel_id)
        if not stream or not stream.playlist_url:
            raise ValueError("No playlist URL returned")

        m3u_content = f"#EXTM3U\n#EXTINF:-1, Tablo Live Channel - {channel_id}\n{stream.playlist_url}\n"
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', channel_id)

        return Response(
            content=m3u_content,
            media_type="application/x-mpegurl",
            headers={
                "Content-Disposition": f'attachment; filename="Tablo_Live_{clean_name}.m3u"',
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating VLC live stream: {e}")


class MeasureRequest(BaseModel):
    channel_id: str


@router.post("/measure")
async def measure_channel(req: MeasureRequest):
    """Antenna helper: tune an antenna channel only to measure its picture quality (no video is
    sent to a player). Read it with /reception/{session_id}; stop it with /stop."""
    if not tablo_manager.is_authenticated:
        raise HTTPException(status_code=400, detail="Tablo device not connected")
    await transcode_manager.wait_for_ended_sessions()
    try:
        stream = await asyncio.to_thread(TabloClient(tablo_manager.device).watch, req.channel_id)
        if not stream or not stream.playlist_url:
            raise ValueError("No playlist URL returned by Tablo")
    except Exception as e:
        print(f"[Antenna] Couldn't tune {req.channel_id}: {e}")
        if isinstance(e, (httpx.TransportError, requests.ConnectionError, requests.Timeout)):
            raise HTTPException(status_code=503, detail=tablo_manager.UNREACHABLE_MESSAGE)
        busy = await all_tuners_busy_message()
        if busy:
            raise HTTPException(status_code=409, detail=busy)
        if _refused(e):
            raise HTTPException(status_code=502, detail=NO_PICKUP_MESSAGE)
        raise HTTPException(status_code=500, detail=f"Couldn't tune this channel: {e}")
    sess = transcode_manager.create_session(stream.playlist_url)
    sess.tablo_token = stream.token
    transcode_manager.start_measure(sess, stream.playlist_url)
    return {"session_id": sess.session_id, "channel_id": req.channel_id}


@router.get("/reception/{session_id}")
async def reception_report(session_id: str):
    """Live picture quality for an antenna channel being watched: the badge's score and state, and
    the last 5 minutes for the graph. Read from FFmpeg's log; nothing is asked of the Tablo."""
    sess = transcode_manager.get_session(session_id)
    if not sess or not sess.reception:
        return {"available": False}
    return {"available": True, **sess.reception.report()}


@router.post("/stop")
async def stop_live_session(req: StopRequest):
    """Stop active live stream transcode session and free up tuner."""
    if req.session_id:
        transcode_manager.stop_session(req.session_id)
    return {"status": "ok"}
