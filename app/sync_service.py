"""Library synchronization service:
Fetches recorded airings, series, and movies from local Tablo 4th Gen DVR,
extracts rich metadata, resolves artwork, and updates the local SQLite cache.
"""

import asyncio
import json
import re
import hashlib
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Dict, Any, List

import httpx

from .tablo_client import tablo_manager
from .notifications import check_all
from . import cleanup, rerecord, returning, signal_health
from .database import (
    upsert_show,
    upsert_episode,
    upsert_guide_show,
    recalculate_show_stats,
    set_sync_meta,
    get_sync_meta,
    prune_obsolete_shows_and_episodes,
    batch_upsert_guide_airings,
    prune_guide_airings,
    clear_stale_schedule_rules,
)


def slugify_show_title(title: str) -> str:
    """Generate a clean consistent ID from show title."""
    cleaned = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned) or hashlib.md5(title.encode(), usedforsecurity=False).hexdigest()[:10]


def extract_image_url(img_obj: Any) -> Optional[str]:
    """Convert Tablo image dict or ID into local proxy URL."""
    if not img_obj:
        return None

    if isinstance(img_obj, dict):
        img_id = img_obj.get("image_id")
        if img_id:
            return f"/api/images/{img_id}"
        if "url" in img_obj:
            return img_obj["url"]

    if isinstance(img_obj, (int, str)):
        if str(img_obj).isdigit():
            return f"/api/images/{img_obj}"
        if str(img_obj).startswith("http"):
            return str(img_obj)

    return None


# Objects per POST /batch. The Tablo closes the connection after every request, and a burst of
# thousands of connections makes it refuse new ones for about a minute; batches avoid that.
BATCH_SIZE = 50
BATCH_PAUSE = 0.2
BATCH_RETRIES = 5
# The Tablo refuses connections for about a minute after too many requests
TABLO_BREAK_SECONDS = 75


async def fetch_objects(paths: List[str], on_chunk: Optional[Callable[[Dict[str, Any]], None]] = None,
                        progress: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch Tablo objects by path, BATCH_SIZE per request. If the Tablo stops answering, wait it out
    and carry on; if it rejects a batch, use smaller ones (down to single GETs). on_chunk gets each
    chunk's results as they arrive; progress (the banner's dict) gets "done" and "waiting_until"."""
    results: Dict[str, Any] = {}
    size = BATCH_SIZE
    i = 0
    retries = 0
    while i < len(paths):
        chunk = paths[i:i + size]
        try:
            if size > 1:
                r = await tablo_manager.request_bulk("POST", "/batch", json.dumps(chunk))
                got = r.json() if r.status_code == 200 else None
                if not isinstance(got, dict):
                    size = max(1, size // 5)
                    print(f"[Sync] The Tablo rejected a batch (HTTP {r.status_code}); using batches of {size}")
                    continue
            else:
                r = await tablo_manager.request_bulk("GET", chunk[0])
                got = {chunk[0]: r.json()} if r.status_code == 200 else {}
        except httpx.TransportError:
            if retries >= BATCH_RETRIES:
                print("[Sync] The Tablo still isn't answering; stopping here")
                break
            retries += 1
            print(f"[Sync] Tablo stopped answering; waiting {TABLO_BREAK_SECONDS} s before continuing")
            if progress is not None:
                progress["waiting_until"] = time.time() + TABLO_BREAK_SECONDS
            await asyncio.sleep(TABLO_BREAK_SECONDS)
            if progress is not None:
                progress["waiting_until"] = None
            continue
        except ValueError:
            got = {}
        retries = 0
        found = {p: d for p, d in got.items() if p in chunk and isinstance(d, dict)}
        results.update(found)
        if on_chunk:
            on_chunk(found)
        i += len(chunk)
        if progress is not None:
            progress["done"] = i
        if i < len(paths):
            await asyncio.sleep(BATCH_PAUSE)
    return results


GUIDE_RETRY_SECONDS = 600  # an unfinished guide load is tried again after this, not GUIDE_SYNC_HOURS


def fetch_incomplete(asked: int, got: int) -> bool:
    """fetch_objects gave up partway (the Tablo stopped answering): more than a handful missing.
    A few can legitimately vanish between listing and fetching (a recording deleted meanwhile)."""
    return asked - got > max(5, asked * 0.02)


def guide_airing_row(p: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """A /guide/... airing object as a guide_airings row (with New / Primetime / Premiere flags)."""
    ep = d.get('episode', {})
    ad = d.get('airing_details', {})
    ch = ad.get('channel', {}).get('channel', {})
    qual = [q.lower() for q in d.get('qualifiers', [])]
    ep_num = ep.get('number') or ep.get('episode_number') or 0
    season_num = ep.get('season_number') or 0
    is_new = 1 if 'new' in qual else 0
    is_premiere = 1 if (
        'season_premiere' in qual or
        'series_premiere' in qual or
        ('premiere' in qual and is_new) or
        (is_new and ep_num == 1 and season_num > 0)
    ) else 0
    # A sports event names its league as sport_path and the game as event.title
    # ("Philadelphia 76ers at New York Knicks" under NBA Basketball)
    ep_title = ep.get('title') or (d.get('event') or {}).get('title')
    if not ep_title:
        ep_title = f"Episode {ep_num}" if ep_num else (ad.get('show_title') or "Episode")
    return {
        "path": p,
        "series_path": d.get('series_path') or d.get('sport_path') or '',
        "show_title": ad.get('show_title') or 'Unknown',
        "episode_title": ep_title,
        "season_number": season_num,
        "episode_number": ep_num,
        "air_datetime": ad.get('datetime') or '',
        "duration": ad.get('duration') or 0,
        "channel_call_sign": ch.get('call_sign') or ch.get('name') or '',
        "channel_identifier": ch.get('channel_identifier'),
        "channel_network": ch.get('network') or '',
        "qualifiers": qual,
        "is_new": is_new,
        "is_primetime": 1 if 'primetime' in qual else 0,
        "is_premiere": is_premiere,
        "schedule_state": (d.get('schedule') or {}).get('state') or 'none',
    }


class LibrarySyncService:
    def __init__(self):
        self.is_syncing = False
        self.is_guide_syncing = False
        self.last_error: Optional[str] = None
        # While the first guide load on this PC runs: shown as a banner.
        # {"first", "step": "shows"|"airings", "done", "total", "started", "waiting_until"}
        self.guide_progress: Optional[Dict[str, Any]] = None
        # The last guide load stopped short: {"missing", "total", "retry_at"} (shown as a banner)
        self.guide_incomplete: Optional[Dict[str, Any]] = None

    async def sync_library(self, include_guide: bool = True) -> Dict[str, Any]:
        """Full synchronization of Tablo DVR library into SQLite cache.
        include_guide=False skips the follow-up guide sync (used by the periodic auto-sync)."""
        if not tablo_manager.is_authenticated:
            raise RuntimeError("Tablo is not authenticated")

        if self.is_syncing:
            return {"status": "already_syncing"}

        self.is_syncing = True
        self.last_error = None

        try:
            print("[LibrarySync] Starting Tablo DVR sync...")

            # 1. Fetch series definitions first
            series_map: Dict[str, Dict[str, Any]] = {}
            try:
                series_resp = await tablo_manager.request_bulk("GET", "/recordings/series")
                if series_resp.status_code == 200:
                    series_paths = series_resp.json()
                    if isinstance(series_paths, list):
                        for sp, s_data in (await fetch_objects(series_paths)).items():
                            s_info = s_data.get("series", {})
                            cover = extract_image_url(s_info.get("cover_image"))
                            thumb = extract_image_url(s_info.get("thumbnail_image"))
                            backdrop = extract_image_url(s_info.get("background_image"))
                            series_map[sp] = {
                                "path": sp,
                                "title": s_info.get("title"),
                                "description": s_info.get("description", ""),
                                "genres": s_info.get("genres", []),
                                "cover_url": cover or thumb,
                                "backdrop_url": backdrop,
                                "raw": s_data
                            }
            except Exception as e:
                print(f"[LibrarySync] Error fetching series paths: {e}")

            # 2. Fetch all recorded airings
            airings_resp = await tablo_manager.request_bulk("GET", "/recordings/airings")
            if airings_resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch airings: HTTP {airings_resp.status_code}")

            airing_paths: List[str] = airings_resp.json()
            if not isinstance(airing_paths, list):
                airing_paths = []

            print(f"[LibrarySync] Found {len(airing_paths)} recorded airing paths. Fetching details...")

            # 3. Fetch the airing objects, in batches
            airings_data: List[Dict[str, Any]] = []
            for path, data in (await fetch_objects(airing_paths)).items():
                data["_path"] = path
                airings_data.append(data)

            print(f"[LibrarySync] Successfully fetched {len(airings_data)} airing records.")
            # If the Tablo stopped answering partway, the recordings not fetched aren't gone: keep them
            # (pruning would drop them from the Library until the next sync)
            partial = fetch_incomplete(len(airing_paths), len(airings_data))
            if partial:
                print(f"[LibrarySync] Only {len(airings_data)} of {len(airing_paths)} recordings came back; "
                      "keeping the rest until the next sync")

            # 4. Group by show and prepare models
            shows_map: Dict[str, Dict[str, Any]] = {}
            episodes_list: List[Dict[str, Any]] = []

            for data in airings_data:
                path = data.get("_path")
                ad = data.get("airing_details", {})
                ep = data.get("episode", {})
                ch = ad.get("channel", {}).get("channel", {})
                user_info = data.get("user_info", {})
                status = "Watched" if user_info.get("watched") else "Unwatched"

                # Resolve show title and series link
                ser_path = data.get("series_path")
                ser_meta = series_map.get(ser_path, {})
                show_title = ser_meta.get("title") or ep.get("show_title") or ad.get("show_title") or "Unknown Show"
                show_id = slugify_show_title(show_title)

                # Duration in seconds
                duration = ad.get("duration", 0)

                # Episode object
                ep_id = f"ep_{data.get('object_id', hashlib.md5(path.encode(), usedforsecurity=False).hexdigest()[:8])}"
                season_num = ep.get("season_number") or 0
                ep_num = ep.get("number") or ep.get("episode_number") or 0
                ep_title = ep.get("title")
                if not ep_title:
                    if ep_num:
                        ep_title = f"Episode {ep_num}"
                    else:
                        ep_title = ad.get("show_title") or "Episode"

                episodes_list.append({
                    "id": ep_id,
                    "show_id": show_id,
                    "show_title": show_title,
                    "path": path,
                    "season_number": season_num,
                    "episode_number": ep_num,
                    "title": ep_title,
                    "description": ep.get("description", "") or ad.get("description", ""),
                    "air_date": ad.get("datetime") or "",
                    "duration": duration,
                    "status": status,
                    "position": user_info.get("position") or 0,
                    "network": ch.get("network", ""),
                    "channel_name": ch.get("call_sign") or ch.get("name", ""),
                    "raw_json": data
                })

                # Aggregate Show
                if show_id not in shows_map:
                    cover_url = ser_meta.get("cover_url")
                    backdrop_url = ser_meta.get("backdrop_url")
                    shows_map[show_id] = {
                        "id": show_id,
                        "title": show_title,
                        "category": "series",
                        "cover_url": cover_url,
                        "backdrop_url": backdrop_url,
                        "description": ser_meta.get("description", ""),
                        "episode_count": 0,
                        "unwatched_count": 0,
                        "latest_recording_date": ad.get("datetime") or "",
                        "path": ser_path or path,
                        "raw_json": ser_meta.get("raw") or data
                    }

                shows_map[show_id]["episode_count"] += 1
                if status != "Watched":
                    shows_map[show_id]["unwatched_count"] += 1

                # Keep latest recording date
                rec_date = ad.get("datetime") or ""
                if rec_date > shows_map[show_id]["latest_recording_date"]:
                    shows_map[show_id]["latest_recording_date"] = rec_date

            # 5. Commit to database
            print(f"[LibrarySync] Saving {len(shows_map)} shows and {len(episodes_list)} episodes to SQLite...")
            for s_data in shows_map.values():
                upsert_show(s_data)

            for ep_data in episodes_list:
                upsert_episode(ep_data)

            # Prune obsolete shows and episodes no longer returned by Tablo (not after a partial fetch)
            if not partial:
                prune_obsolete_shows_and_episodes(list(shows_map.keys()), [e["id"] for e in episodes_list])
            else:
                for show_id in shows_map:  # counts from all the recordings kept, not just those fetched
                    recalculate_show_stats(show_id)

            now_iso = datetime.now(timezone.utc).isoformat()
            set_sync_meta("last_sync", now_iso)
            set_sync_meta("total_shows", str(len(shows_map)))
            set_sync_meta("total_episodes", str(len(episodes_list)))

            # Also sync guide in background task (it checks for conflicts when done)
            if include_guide:
                asyncio.create_task(self.sync_guide())
            await check_all(conflicts=not include_guide)
            await cleanup.run()
            await rerecord.run()
            await asyncio.to_thread(signal_health.check)

            print("[LibrarySync] Library sync finished successfully!")
            return {
                "status": "success",
                "shows_count": len(shows_map),
                "episodes_count": len(episodes_list),
                "synced_at": now_iso
            }

        except Exception as e:
            self.last_error = str(e)
            print(f"[LibrarySync] Sync error: {e}")
            raise
        finally:
            self.is_syncing = False

    async def sync_guide(self) -> Dict[str, Any]:
        """Fetch and cache all OTA broadcast guide series, movies, and sports into SQLite.
        Only one guide sync runs at a time; overlapping triggers are skipped."""
        if not tablo_manager.is_authenticated:
            raise RuntimeError("Tablo is not authenticated")

        if self.is_guide_syncing:
            return {"status": "already_syncing"}

        self.is_guide_syncing = True
        try:
            result = await self._sync_guide()
        finally:
            self.is_guide_syncing = False
            self.guide_progress = None
        await check_all(recordings=False)
        await rerecord.run()
        await asyncio.to_thread(returning.check)
        return result

    async def _sync_guide(self) -> Dict[str, Any]:
        print("[GuideSync] Starting OTA Guide sync...")
        first = not get_sync_meta("last_guide_sync")
        if first:
            self.guide_progress = {"first": True, "step": "shows", "done": 0, "total": 0,
                                   "started": time.time(), "waiting_until": None}
        guide_endpoints = [
            ("GET", "/guide/series", "series"),
            ("GET", "/guide/movies", "movies"),
            ("GET", "/guide/sports", "sports"),
        ]

        total_synced = 0

        for method, endpoint, cat in guide_endpoints:
            try:
                resp = await tablo_manager.request_bulk(method, endpoint)
                if resp.status_code != 200:
                    continue
                paths = resp.json()
                if not isinstance(paths, list):
                    continue

                # The plain list only has shows airing in the ~2-week guide window. Series with a
                # recording rule but no current airings (e.g. between seasons) come from this filter.
                scheduled_paths = None
                try:
                    sched_resp = await tablo_manager.request_bulk(method, f"{endpoint}?state=scheduled")
                    if sched_resp.status_code == 200 and isinstance(sched_resp.json(), list):
                        scheduled_paths = sched_resp.json()
                        extra = [p for p in scheduled_paths if p not in set(paths)]
                        if extra:
                            print(f"[GuideSync] {len(extra)} scheduled {cat} with no current airings")
                        paths = paths + extra
                except Exception as e:
                    print(f"[GuideSync] Couldn't list scheduled {cat}: {e}")

                for p, d in (await fetch_objects(paths, progress=self.guide_progress)).items():
                    info = d.get(cat) or d.get("series") or d.get("movie") or d.get("sport") or {}
                    counts = d.get("show_counts") or {}
                    upsert_guide_show({
                        "path": p,
                        "object_id": d.get("object_id"),
                        "title": info.get("title") or d.get("title") or "Unknown",
                        "category": cat,
                        "description": info.get("description") or d.get("description") or "",
                        "cover_url": extract_image_url(info.get("cover_image") or info.get("thumbnail_image")),
                        "backdrop_url": extract_image_url(info.get("background_image")),
                        "genres": info.get("genres") or [],
                        "schedule_rule": d.get("schedule_rule") or (d.get("schedule") or {}).get("rule") or "none",
                        "airing_count": counts.get("airing_count", 0),
                        "scheduled_count": counts.get("scheduled_count", 0),
                        "orig_air_date": info.get("orig_air_date", ""),
                        "recordings_path": d.get("recordings_path", ""),
                        "raw_json": d
                    })
                    total_synced += 1
                if scheduled_paths is not None:
                    cleared = clear_stale_schedule_rules(cat, scheduled_paths)
                    if cleared:
                        print(f"[GuideSync] {cleared} {cat} no longer scheduled on the Tablo")
            except Exception as e:
                print(f"[GuideSync] Error syncing {endpoint}: {e}")

        now_iso = datetime.now(timezone.utc).isoformat()
        set_sync_meta("last_guide_sync", now_iso)
        set_sync_meta("total_guide_shows", str(total_synced))
        print(f"[GuideSync] Finished guide show catalog sync! Cached {total_synced} guide entries.")

        # Also sync all upcoming guide airings to detect Primetime New and Season Premieres
        incomplete: Optional[Dict[str, Any]] = {"missing": None, "total": None}  # until the airings arrive
        try:
            print("[GuideSync] Syncing upcoming broadcast airings for Primetime & Premiere detection...")
            airings_resp = await tablo_manager.request_bulk("GET", "/guide/airings")
            if airings_resp.status_code == 200:
                airing_paths = airings_resp.json()
                if isinstance(airing_paths, list):
                    prune_guide_airings(airing_paths)
                    print(f"[GuideSync] Fetching {len(airing_paths)} upcoming airings")
                    if first:
                        self.guide_progress = {"first": first, "step": "airings", "done": 0, "total": len(airing_paths),
                                               "started": time.time(), "waiting_until": None}
                    # Saved as each batch arrives, so the Guide fills in during a first load
                    saved = 0

                    def save(chunk: Dict[str, Any]) -> None:
                        nonlocal saved
                        rows = [guide_airing_row(p, d) for p, d in chunk.items()]
                        batch_upsert_guide_airings(rows)
                        saved += len(rows)

                    await fetch_objects(airing_paths, on_chunk=save, progress=self.guide_progress)
                    print(f"[GuideSync] Saved {saved} upcoming airings with Primetime & Premiere tags.")
                    incomplete = ({"missing": len(airing_paths) - saved, "total": len(airing_paths)}
                                  if fetch_incomplete(len(airing_paths), saved) else None)
        except Exception as e:
            print(f"[GuideSync] Error syncing guide airings: {e}")

        # An unfinished load leaves gaps (recordings missing from Scheduled): say so, and try again
        # in GUIDE_RETRY_SECONDS rather than GUIDE_SYNC_HOURS (auto_sync_loop)
        if incomplete:
            self.guide_incomplete = {**incomplete, "retry_at": time.time() + GUIDE_RETRY_SECONDS}
            print(f"[GuideSync] The guide didn't finish loading ({incomplete['missing']} of {incomplete['total']} "
                  f"airings missing); trying again in {GUIDE_RETRY_SECONDS // 60} minutes")
        else:
            self.guide_incomplete = None
        return {"status": "success" if not incomplete else "incomplete", "count": total_synced, "synced_at": now_iso}


def _age_seconds(iso: Optional[str]) -> float:
    if not iso:
        return float("inf")
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return float("inf")


async def auto_sync_loop(service: "LibrarySyncService"):
    """Background schedule: recordings every N minutes (setting), guide every GUIDE_SYNC_HOURS.
    Re-reads settings each minute so changes on the Device page apply without a restart."""
    from .settings import load_settings, GUIDE_SYNC_HOURS
    from .database import get_sync_meta

    while True:
        await asyncio.sleep(60)
        try:
            if not tablo_manager.is_authenticated:
                continue
            minutes = int(load_settings().get("auto_sync_minutes") or 0)
            if minutes > 0 and not service.is_syncing and _age_seconds(get_sync_meta("last_sync")) >= minutes * 60:
                print(f"[AutoSync] Recordings (every {minutes} min)")
                await service.sync_library(include_guide=False)
            if (minutes > 0 and not service.is_guide_syncing
                    and _age_seconds(get_sync_meta("last_guide_sync")) >= GUIDE_SYNC_HOURS * 3600):
                print(f"[AutoSync] Guide (every {GUIDE_SYNC_HOURS} h)")
                await service.sync_guide()
            elif (service.guide_incomplete and not service.is_guide_syncing
                    and time.time() >= service.guide_incomplete["retry_at"]):
                print("[AutoSync] Guide (the last load didn't finish)")
                await service.sync_guide()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[AutoSync] {e}")


sync_service = LibrarySyncService()
