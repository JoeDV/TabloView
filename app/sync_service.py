"""Library synchronization service:
Fetches recorded airings, series, and movies from local Tablo 4th Gen DVR,
extracts rich metadata, resolves artwork, and updates the local SQLite cache.
"""

import asyncio
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .tablo_client import tablo_manager
from .notifications import check_all
from . import cleanup
from .database import (
    upsert_show,
    upsert_episode,
    upsert_guide_show,
    recalculate_show_stats,
    set_sync_meta,
    prune_obsolete_shows_and_episodes,
    batch_upsert_guide_airings,
    guide_airings_to_fetch,
    clear_stale_schedule_rules,
)


def slugify_show_title(title: str) -> str:
    """Generate a clean consistent ID from show title."""
    cleaned = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned) or hashlib.md5(title.encode()).hexdigest()[:10]


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


class LibrarySyncService:
    def __init__(self):
        self.is_syncing = False
        self.is_guide_syncing = False
        self.last_error: Optional[str] = None

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
                        sem_series = asyncio.Semaphore(15)

                        async def fetch_series(sp: str):
                            async with sem_series:
                                try:
                                    s_res = await tablo_manager.request_bulk("GET", sp)
                                    if s_res.status_code == 200:
                                        s_data = s_res.json()
                                        s_info = s_data.get("series", {})
                                        title = s_info.get("title")
                                        cover = extract_image_url(s_info.get("cover_image"))
                                        thumb = extract_image_url(s_info.get("thumbnail_image"))
                                        backdrop = extract_image_url(s_info.get("background_image"))
                                        series_map[sp] = {
                                            "path": sp,
                                            "title": title,
                                            "description": s_info.get("description", ""),
                                            "genres": s_info.get("genres", []),
                                            "cover_url": cover or thumb,
                                            "backdrop_url": backdrop,
                                            "raw": s_data
                                        }
                                except Exception as e:
                                    print(f"Error fetching series {sp}: {e}")

                        await asyncio.gather(*[fetch_series(sp) for sp in series_paths])
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

            # 3. Concurrently fetch individual airing objects
            airings_data: List[Dict[str, Any]] = []
            sem = asyncio.Semaphore(20)

            async def fetch_airing(path: str):
                async with sem:
                    try:
                        res = await tablo_manager.request_bulk("GET", path)
                        if res.status_code == 200:
                            data = res.json()
                            data["_path"] = path
                            return data
                    except Exception as e:
                        print(f"Failed to fetch airing {path}: {e}")
                    return None

            tasks = [fetch_airing(p) for p in airing_paths]
            results = await asyncio.gather(*tasks)
            airings_data = [r for r in results if r]

            print(f"[LibrarySync] Successfully fetched {len(airings_data)} airing records.")

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
                ep_id = f"ep_{data.get('object_id', hashlib.md5(path.encode()).hexdigest()[:8])}"
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

            # Prune obsolete shows and episodes no longer returned by Tablo
            prune_obsolete_shows_and_episodes(list(shows_map.keys()), [e["id"] for e in episodes_list])

            now_iso = datetime.now(timezone.utc).isoformat()
            set_sync_meta("last_sync", now_iso)
            set_sync_meta("total_shows", str(len(shows_map)))
            set_sync_meta("total_episodes", str(len(episodes_list)))

            # Also sync guide in background task (it checks for conflicts when done)
            if include_guide:
                asyncio.create_task(self.sync_guide())
            await check_all(conflicts=not include_guide)
            await cleanup.run()

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
        await check_all(recordings=False)
        return result

    async def _sync_guide(self) -> Dict[str, Any]:
        print("[GuideSync] Starting OTA Guide sync...")
        guide_endpoints = [
            ("GET", "/guide/series", "series"),
            ("GET", "/guide/movies", "movies"),
            ("GET", "/guide/sports", "sports"),
        ]

        total_synced = 0
        sem = asyncio.Semaphore(25)

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

                async def fetch_item(p: str):
                    async with sem:
                        try:
                            r = await tablo_manager.request_bulk("GET", p)
                            if r.status_code == 200:
                                d = r.json()
                                info = d.get(cat) or d.get("series") or d.get("movie") or d.get("sport") or {}
                                title = info.get("title") or d.get("title") or "Unknown"
                                desc = info.get("description") or d.get("description") or ""
                                genres = info.get("genres") or []
                                cover = extract_image_url(info.get("cover_image") or info.get("thumbnail_image"))
                                backdrop = extract_image_url(info.get("background_image"))
                                counts = d.get("show_counts") or {}
                                rule = d.get("schedule_rule") or (d.get("schedule") or {}).get("rule") or "none"

                                upsert_guide_show({
                                    "path": p,
                                    "object_id": d.get("object_id"),
                                    "title": title,
                                    "category": cat,
                                    "description": desc,
                                    "cover_url": cover,
                                    "backdrop_url": backdrop,
                                    "genres": genres,
                                    "schedule_rule": rule,
                                    "airing_count": counts.get("airing_count", 0),
                                    "scheduled_count": counts.get("scheduled_count", 0),
                                    "orig_air_date": info.get("orig_air_date", ""),
                                    "recordings_path": d.get("recordings_path", ""),
                                    "raw_json": d
                                })
                                return 1
                        except Exception:
                            pass
                        return 0

                results = await asyncio.gather(*[fetch_item(p) for p in paths])
                total_synced += sum(results)
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
        try:
            print("[GuideSync] Syncing upcoming broadcast airings for Primetime & Premiere detection...")
            airings_resp = await tablo_manager.request_bulk("GET", "/guide/airings")
            if airings_resp.status_code == 200:
                airing_paths = airings_resp.json()
                if isinstance(airing_paths, list):
                    listed = len(airing_paths)
                    airing_paths = guide_airings_to_fetch(airing_paths)
                    print(f"[GuideSync] {listed} upcoming airings; fetching {len(airing_paths)} new or record-status ones")
                    # A first sync (empty cache) fetches thousands: pace them so the Tablo keeps answering
                    pace = len(airing_paths) > 300
                    sem_air = asyncio.Semaphore(2 if pace else 50)
                    async def fetch_guide_airing(p: str):
                        async with sem_air:
                            try:
                                r = await tablo_manager.request_bulk("GET", p)
                                if pace:
                                    await asyncio.sleep(0.1)
                                if r.status_code == 200:
                                    d = r.json()
                                    ep = d.get('episode', {})
                                    ad = d.get('airing_details', {})
                                    ch = ad.get('channel', {}).get('channel', {})
                                    qual = [q.lower() for q in d.get('qualifiers', [])]
                                    ep_num = ep.get('number') or ep.get('episode_number') or 0
                                    season_num = ep.get('season_number') or 0
                                    
                                    is_new = 1 if 'new' in qual else 0
                                    is_primetime = 1 if 'primetime' in qual else 0
                                    is_premiere = 1 if (
                                        'season_premiere' in qual or 
                                        'series_premiere' in qual or 
                                        ('premiere' in qual and is_new) or 
                                        (is_new and ep_num == 1 and season_num > 0)
                                    ) else 0

                                    ep_title = ep.get('title')
                                    if not ep_title:
                                        ep_title = f"Episode {ep_num}" if ep_num else (ad.get('show_title') or "Episode")

                                    return {
                                        "path": p,
                                        "series_path": d.get('series_path') or '',
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
                                        "is_primetime": is_primetime,
                                        "is_premiere": is_premiere,
                                        "schedule_state": (d.get('schedule') or {}).get('state') or 'none',
                                    }
                            except Exception:
                                pass
                            return None

                    airing_results = await asyncio.gather(*[fetch_guide_airing(p) for p in airing_paths])
                    valid_airings = [a for a in airing_results if a]
                    batch_upsert_guide_airings(valid_airings)
                    print(f"[GuideSync] Saved {len(valid_airings)} upcoming airings with Primetime & Premiere tags.")
        except Exception as e:
            print(f"[GuideSync] Error syncing guide airings: {e}")

        return {"status": "success", "count": total_synced, "synced_at": now_iso}


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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[AutoSync] {e}")


sync_service = LibrarySyncService()
