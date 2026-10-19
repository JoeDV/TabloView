"""SQLite Database layer for Tablo Classic UI caching."""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from .config import DB_FILE


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Shows table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shows (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'series',
                cover_url TEXT,
                backdrop_url TEXT,
                description TEXT,
                episode_count INTEGER DEFAULT 0,
                unwatched_count INTEGER DEFAULT 0,
                latest_recording_date TEXT,
                path TEXT,
                raw_json TEXT,
                updated_at TEXT
            )
        """)

        # Episodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                show_id TEXT NOT NULL,
                show_title TEXT NOT NULL,
                path TEXT NOT NULL,
                season_number INTEGER DEFAULT 0,
                episode_number INTEGER DEFAULT 0,
                title TEXT,
                description TEXT,
                air_date TEXT,
                duration INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Unwatched',
                network TEXT,
                channel_name TEXT,
                raw_json TEXT,
                updated_at TEXT,
                FOREIGN KEY (show_id) REFERENCES shows(id) ON DELETE CASCADE
            )
        """)

        # Exports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exports (
                job_id TEXT PRIMARY KEY,
                episode_id TEXT,
                title TEXT,
                filename TEXT,
                filepath TEXT,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0.0,
                file_size INTEGER DEFAULT 0,
                error TEXT,
                created_at TEXT,
                completed_at TEXT
            )
        """)

        # Metadata table (last sync, hard drive stats, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        # Guide Shows table (OTA broadcast guide items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guide_shows (
                path TEXT PRIMARY KEY,
                object_id INTEGER,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'series',
                description TEXT,
                cover_url TEXT,
                backdrop_url TEXT,
                genres TEXT,
                schedule_rule TEXT DEFAULT 'none',
                airing_count INTEGER DEFAULT 0,
                scheduled_count INTEGER DEFAULT 0,
                orig_air_date TEXT,
                recordings_path TEXT,
                raw_json TEXT,
                updated_at TEXT
            )
        """)

        # Guide Airings table (all upcoming broadcast airings with qualifiers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guide_airings (
                path TEXT PRIMARY KEY,
                series_path TEXT,
                show_title TEXT NOT NULL,
                episode_title TEXT,
                season_number INTEGER DEFAULT 0,
                episode_number INTEGER DEFAULT 0,
                air_datetime TEXT,
                duration INTEGER DEFAULT 0,
                channel_call_sign TEXT,
                channel_network TEXT,
                qualifiers TEXT,
                is_new INTEGER DEFAULT 0,
                is_primetime INTEGER DEFAULT 0,
                is_premiere INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)

        # Commercial breaks found in recordings (app/commercials.py), by episode id.
        # status: done (breaks_json set), unreliable (show and ads couldn't be told apart), failed
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commercials (
                episode_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                breaks_json TEXT,
                error TEXT,
                analyzed_at TEXT
            )
        """)

        # Columns added after the first release (CREATE TABLE IF NOT EXISTS won't add them)
        ga_cols = {r[1] for r in cursor.execute("PRAGMA table_info(guide_airings)").fetchall()}
        if "schedule_state" not in ga_cols:
            cursor.execute("ALTER TABLE guide_airings ADD COLUMN schedule_state TEXT DEFAULT 'none'")
        if "channel_identifier" not in ga_cols:
            # Stable channel ID (e.g. S36147_029_01), same as the Live TV channel list uses
            cursor.execute("ALTER TABLE guide_airings ADD COLUMN channel_identifier TEXT")
        ep_cols = {r[1] for r in cursor.execute("PRAGMA table_info(episodes)").fetchall()}
        if "position" not in ep_cols:
            # Resume point in seconds, as stored on the Tablo (user_info.position)
            cursor.execute("ALTER TABLE episodes ADD COLUMN position INTEGER DEFAULT 0")

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_show_id ON episodes(show_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_air_date ON episodes(air_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shows_latest_rec ON shows(latest_recording_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shows_title ON shows(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_guide_shows_title ON guide_shows(title)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_guide_shows_rule ON guide_shows(schedule_rule)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_guide_shows_cat ON guide_shows(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ga_series_path ON guide_airings(series_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ga_air_datetime ON guide_airings(air_datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ga_primetime_new ON guide_airings(is_new, is_primetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ga_premiere ON guide_airings(is_premiere)")
        conn.commit()


def get_sync_meta(key: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_sync_meta(key: str, value: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO sync_meta (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, value, now))
        conn.commit()


def upsert_show(show_data: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    raw = json.dumps(show_data.get("raw_json", {})) if isinstance(show_data.get("raw_json"), (dict, list)) else show_data.get("raw_json", "")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO shows (
                id, title, category, cover_url, backdrop_url, description,
                episode_count, unwatched_count, latest_recording_date, path, raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                cover_url = COALESCE(excluded.cover_url, shows.cover_url),
                backdrop_url = COALESCE(excluded.backdrop_url, shows.backdrop_url),
                description = COALESCE(excluded.description, shows.description),
                episode_count = excluded.episode_count,
                unwatched_count = excluded.unwatched_count,
                latest_recording_date = excluded.latest_recording_date,
                path = excluded.path,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
        """, (
            show_data["id"],
            show_data["title"],
            show_data.get("category", "series"),
            show_data.get("cover_url"),
            show_data.get("backdrop_url"),
            show_data.get("description", ""),
            show_data.get("episode_count", 0),
            show_data.get("unwatched_count", 0),
            show_data.get("latest_recording_date", ""),
            show_data.get("path", ""),
            raw,
            now
        ))
        conn.commit()


def upsert_episode(ep_data: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    raw = json.dumps(ep_data.get("raw_json", {})) if isinstance(ep_data.get("raw_json"), (dict, list)) else ep_data.get("raw_json", "")
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO episodes (
                id, show_id, show_title, path, season_number, episode_number,
                title, description, air_date, duration, status, network, channel_name, raw_json, updated_at,
                position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                position = excluded.position,
                show_id = excluded.show_id,
                show_title = excluded.show_title,
                path = excluded.path,
                season_number = excluded.season_number,
                episode_number = excluded.episode_number,
                title = excluded.title,
                description = excluded.description,
                air_date = excluded.air_date,
                duration = excluded.duration,
                status = excluded.status,
                network = excluded.network,
                channel_name = excluded.channel_name,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
        """, (
            ep_data["id"],
            ep_data["show_id"],
            ep_data["show_title"],
            ep_data["path"],
            ep_data.get("season_number", 0),
            ep_data.get("episode_number", 0),
            ep_data.get("title", ""),
            ep_data.get("description", ""),
            ep_data.get("air_date", ""),
            ep_data.get("duration", 0),
            ep_data.get("status", "Unwatched"),
            ep_data.get("network", ""),
            ep_data.get("channel_name", ""),
            raw,
            now,
            int(ep_data.get("position") or 0),
        ))
        conn.commit()


def get_shows(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recent"
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM shows WHERE episode_count > 0"
    params = []

    if category and category.lower() != "all":
        query += " AND category = ?"
        params.append(category.lower())

    if search and search.strip():
        query += " AND title LIKE ?"
        params.append(f"%{search.strip()}%")

    if sort_by == "alphabetical":
        query += " ORDER BY title COLLATE NOCASE ASC"
    elif sort_by == "episodes":
        query += " ORDER BY episode_count DESC, title COLLATE NOCASE ASC"
    else:  # recent default
        query += " ORDER BY latest_recording_date DESC, title COLLATE NOCASE ASC"

    with get_connection() as conn:
        shows = [dict(r) for r in conn.execute(query, params).fetchall()]
        incomplete: Dict[str, int] = {}
        for r in conn.execute("SELECT show_id, raw_json FROM episodes").fetchall():
            if recording_details(r["raw_json"])["incomplete"]:
                incomplete[r["show_id"]] = incomplete.get(r["show_id"], 0) + 1
    for s in shows:
        s["incomplete_count"] = incomplete.get(s["id"], 0)
    return shows


def get_show_by_id(show_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
        return dict(row) if row else None


# A finished recording that stopped more than this many seconds before the show's scheduled end
SHORT_RECORDING_SECONDS = 60


def recording_details(raw_json: Any) -> Dict[str, Any]:
    """Fields from the Tablo's own recording object (kept in raw_json at sync)."""
    try:
        raw = json.loads(raw_json or "{}") if isinstance(raw_json, str) else (raw_json or {})
    except (TypeError, ValueError):
        raw = {}
    vd = raw.get("video_details") or {}
    state = vd.get("state")
    # recorded_offsets.end: seconds past the scheduled end (negative = stopped early)
    ended_early = -int((vd.get("recorded_offsets") or {}).get("end") or 0)
    snap = (raw.get("snapshot_image") or {}).get("image_id")
    return {
        "recording_state": state,
        "recording_error": vd.get("error"),
        "actual_duration": vd.get("duration"),
        "ended_early": ended_early if state == "finished" and ended_early > SHORT_RECORDING_SECONDS else 0,
        "incomplete": state == "failed" or (state == "finished" and ended_early > SHORT_RECORDING_SECONDS),
        "protected": bool((raw.get("user_info") or {}).get("protected")),
        "snapshot_url": f"/api/images/{snap}" if str(snap or "").isdigit() else None,
        # Where the program itself starts: the Tablo begins recording a little early
        "program_start": max(0, int(vd.get("seek") or 0)),
    }


def get_episodes_by_show(show_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM episodes
            WHERE show_id = ?
            ORDER BY
                CASE WHEN season_number > 0 THEN season_number ELSE 9999 END ASC,
                CASE WHEN episode_number > 0 THEN episode_number ELSE 9999 END ASC,
                air_date ASC
        """, (show_id,)).fetchall()
        return [{**dict(r), **recording_details(r["raw_json"])} for r in rows]


def get_episode_by_id(episode_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ? OR path = ?", (episode_id, episode_id)).fetchone()
        return {**dict(row), **recording_details(row["raw_json"])} if row else None


def set_episode_progress(episode_id: str, position: Optional[int] = None, watched: Optional[bool] = None):
    """Mirror a watched/position change made on the Tablo into the cache and refresh show counts."""
    with get_connection() as conn:
        row = conn.execute("SELECT show_id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not row:
            return
        if position is not None:
            # On the Tablo, saving a position also marks the recording unwatched
            conn.execute("UPDATE episodes SET position = ?, status = 'Unwatched' WHERE id = ?", (int(position), episode_id))
        if watched is not None:
            conn.execute("UPDATE episodes SET status = ? WHERE id = ?", ("Watched" if watched else "Unwatched", episode_id))
        conn.commit()
    recalculate_show_stats(row["show_id"])


def _patch_raw(table: str, row_id: str, change) -> None:
    """Apply change(raw_dict) to a cached Tablo object, so the UI reflects an edit before the next sync."""
    with get_connection() as conn:
        row = conn.execute(f"SELECT raw_json FROM {table} WHERE id = ?", (row_id,)).fetchone()
        if not row:
            return
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except ValueError:
            raw = {}
        change(raw)
        conn.execute(f"UPDATE {table} SET raw_json = ? WHERE id = ?", (json.dumps(raw), row_id))
        conn.commit()


def set_episode_protected(episode_id: str, protected: bool) -> None:
    _patch_raw("episodes", episode_id, lambda raw: raw.setdefault("user_info", {}).update(protected=protected))


def show_keep(show: Optional[Dict[str, Any]]) -> Optional[int]:
    """The Tablo's keep rule for a recorded series: how many of the newest recordings it keeps (None = all)."""
    try:
        raw = json.loads((show or {}).get("raw_json") or "{}")
    except (TypeError, ValueError):
        return None
    keep = raw.get("keep") or {}
    return int(keep["count"]) if keep.get("rule") == "count" and keep.get("count") else None


def set_show_keep(show_id: str, keep: Dict[str, Any]) -> None:
    _patch_raw("shows", show_id, lambda raw: raw.update(keep=keep))


def save_commercials(episode_id: str, status: str, breaks: Optional[List[Dict[str, float]]] = None,
                     error: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO commercials (episode_id, status, breaks_json, error, analyzed_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(episode_id) DO UPDATE SET status = excluded.status, breaks_json = excluded.breaks_json,
                error = excluded.error, analyzed_at = excluded.analyzed_at
        """, (episode_id, status, json.dumps(breaks) if breaks is not None else None, error,
              datetime.now(timezone.utc).isoformat()))
        conn.commit()


def get_commercials(episode_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """episode_id -> {'status', 'breaks', 'error'}."""
    with get_connection() as conn:
        if episode_ids is None:
            rows = conn.execute("SELECT * FROM commercials").fetchall()
        else:
            marks = ",".join("?" * len(episode_ids)) or "''"
            rows = conn.execute(f"SELECT * FROM commercials WHERE episode_id IN ({marks})", episode_ids).fetchall()
    return {r["episode_id"]: {"status": r["status"], "breaks": json.loads(r["breaks_json"]) if r["breaks_json"] else [],
                              "error": r["error"]} for r in rows}


def get_watched_episodes() -> List[Dict[str, Any]]:
    """Every watched recording, for the automatic cleanup."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, show_id, show_title, title, season_number, episode_number, path, raw_json
            FROM episodes WHERE status = 'Watched'
        """).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["protected"] = recording_details(d.pop("raw_json"))["protected"]
        result.append(d)
    return result


def get_incomplete_recordings() -> List[Dict[str, Any]]:
    """Recordings that failed or stopped early (see recording_details), newest first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, show_title, title, season_number, episode_number, duration, air_date, raw_json
            FROM episodes ORDER BY air_date DESC
        """).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.update(recording_details(d.pop("raw_json")))
        if d["incomplete"]:
            result.append(d)
    return result


def get_storage_by_show() -> List[Dict[str, Any]]:
    """Space per recorded show, biggest first, from each recording's size as the Tablo reports it
    (video_details.size, in bytes). These sizes don't add up to the drive's usage figure, so callers
    should treat them as each show's share rather than exact amounts."""
    shows: Dict[str, Dict[str, Any]] = {}
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.show_id, e.status, e.air_date, e.raw_json, s.title, s.cover_url, s.backdrop_url
            FROM episodes e JOIN shows s ON s.id = e.show_id
        """).fetchall()
    for r in rows:
        try:
            raw = json.loads(r["raw_json"] or "{}")
        except ValueError:
            raw = {}
        size = int((raw.get("video_details") or {}).get("size") or 0)
        s = shows.setdefault(r["show_id"], {
            "show_id": r["show_id"], "title": r["title"], "cover_url": r["cover_url"] or r["backdrop_url"],
            "count": 0, "bytes": 0, "watched_count": 0, "watched_bytes": 0, "protected_watched": 0,
        })
        s["count"] += 1
        s["bytes"] += size
        if r["status"] == "Watched":
            if (raw.get("user_info") or {}).get("protected"):
                s["protected_watched"] += 1
            else:
                s["watched_count"] += 1
                s["watched_bytes"] += size
    return sorted(shows.values(), key=lambda s: s["bytes"], reverse=True)


def get_in_progress_episodes(limit: int = 20) -> List[Dict[str, Any]]:
    """Partly watched recordings (resume point saved, not finished), newest airing first.
    (The Tablo doesn't record when something was last watched, so air date is the best order.)"""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.id, e.show_id, e.show_title, e.title, e.season_number, e.episode_number,
                   e.duration, e.position, e.air_date, e.raw_json, s.cover_url, s.backdrop_url
            FROM episodes e LEFT JOIN shows s ON s.id = e.show_id
            WHERE e.position > 0 AND e.status != 'Watched'
            ORDER BY e.air_date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d.update(recording_details(d.pop("raw_json")))
            result.append(d)
        return result


def delete_episode(episode_id: str) -> Optional[str]:
    """Delete episode from db and return its show_id to recalculate stats."""
    with get_connection() as conn:
        row = conn.execute("SELECT show_id FROM episodes WHERE id = ? OR path = ?", (episode_id, episode_id)).fetchone()
        if not row:
            return None
        show_id = row["show_id"]
        conn.execute("DELETE FROM episodes WHERE id = ? OR path = ?", (episode_id, episode_id))
        conn.commit()
        recalculate_show_stats(show_id)
        return show_id


def recalculate_show_stats(show_id: str):
    """Update show's episode_count, unwatched_count, and latest_recording_date."""
    with get_connection() as conn:
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN status != 'Watched' THEN 1 ELSE 0 END) as unwatched_count,
                MAX(air_date) as latest_date
            FROM episodes
            WHERE show_id = ?
        """, (show_id,)).fetchone()

        total = stats["total_count"] if stats else 0
        unwatched = stats["unwatched_count"] if stats else 0
        latest = stats["latest_date"] if stats else ""

        if total == 0:
            conn.execute("UPDATE shows SET episode_count = 0, unwatched_count = 0 WHERE id = ?", (show_id,))
        else:
            conn.execute("""
                UPDATE shows 
                SET episode_count = ?, unwatched_count = ?, latest_recording_date = COALESCE(?, latest_recording_date)
                WHERE id = ?
            """, (total, unwatched, latest, show_id))
        conn.commit()


def prune_obsolete_shows_and_episodes(valid_show_ids: List[str], valid_ep_ids: List[str]):
    """Remove any shows or episodes from the cache that are no longer present on the Tablo DVR."""
    with get_connection() as conn:
        if valid_show_ids:
            placeholders_s = ",".join("?" * len(valid_show_ids))
            conn.execute(f"DELETE FROM shows WHERE id NOT IN ({placeholders_s})", valid_show_ids)
        if valid_ep_ids:
            placeholders_e = ",".join("?" * len(valid_ep_ids))
            conn.execute(f"DELETE FROM episodes WHERE id NOT IN ({placeholders_e})", valid_ep_ids)
        conn.commit()


def save_export_job(job: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO exports (
                job_id, episode_id, title, filename, filepath, status, progress, file_size, error, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                progress = excluded.progress,
                file_size = excluded.file_size,
                error = excluded.error,
                completed_at = excluded.completed_at
        """, (
            job["job_id"],
            job.get("episode_id", ""),
            job.get("title", ""),
            job.get("filename", ""),
            job.get("filepath", ""),
            job.get("status", "pending"),
            job.get("progress", 0.0),
            job.get("file_size", 0),
            job.get("error", None),
            job.get("created_at", now),
            job.get("completed_at", None)
        ))
        conn.commit()


def delete_export_job(job_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM exports WHERE job_id = ?", (job_id,))
        conn.commit()


def get_export_jobs() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM exports ORDER BY created_at DESC LIMIT 50").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Guide Shows Database Functions
# ---------------------------------------------------------------------------

def upsert_guide_show(data: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    raw = json.dumps(data.get("raw_json", {})) if isinstance(data.get("raw_json"), (dict, list)) else data.get("raw_json", "")
    genres_val = json.dumps(data.get("genres", [])) if isinstance(data.get("genres"), list) else str(data.get("genres", "[]"))
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO guide_shows (
                path, object_id, title, category, description, cover_url, backdrop_url,
                genres, schedule_rule, airing_count, scheduled_count, orig_air_date,
                recordings_path, raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                object_id = COALESCE(excluded.object_id, guide_shows.object_id),
                title = excluded.title,
                category = excluded.category,
                description = COALESCE(excluded.description, guide_shows.description),
                cover_url = COALESCE(excluded.cover_url, guide_shows.cover_url),
                backdrop_url = COALESCE(excluded.backdrop_url, guide_shows.backdrop_url),
                genres = excluded.genres,
                schedule_rule = excluded.schedule_rule,
                airing_count = excluded.airing_count,
                scheduled_count = excluded.scheduled_count,
                orig_air_date = excluded.orig_air_date,
                recordings_path = excluded.recordings_path,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
        """, (
            data["path"],
            data.get("object_id"),
            data["title"],
            data.get("category", "series"),
            data.get("description", ""),
            data.get("cover_url"),
            data.get("backdrop_url"),
            genres_val,
            data.get("schedule_rule", "none"),
            data.get("airing_count", 0),
            data.get("scheduled_count", 0),
            data.get("orig_air_date", ""),
            data.get("recordings_path", ""),
            raw,
            now
        ))
        conn.commit()


def batch_upsert_guide_airings(airings: List[Dict[str, Any]]):
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            a["path"],
            a.get("series_path", ""),
            a.get("show_title", ""),
            a.get("episode_title", ""),
            a.get("season_number", 0),
            a.get("episode_number", 0),
            a.get("air_datetime", ""),
            a.get("duration", 0),
            a.get("channel_call_sign", ""),
            a.get("channel_network", ""),
            json.dumps(a.get("qualifiers", [])),
            1 if a.get("is_new") else 0,
            1 if a.get("is_primetime") else 0,
            1 if a.get("is_premiere") else 0,
            a.get("schedule_state") or "none",
            a.get("channel_identifier"),
            now
        ) for a in airings
    ]
    with get_connection() as conn:
        conn.executemany("""
            INSERT INTO guide_airings (
                path, series_path, show_title, episode_title, season_number, episode_number,
                air_datetime, duration, channel_call_sign, channel_network, qualifiers,
                is_new, is_primetime, is_premiere, schedule_state, channel_identifier, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                series_path = excluded.series_path,
                show_title = excluded.show_title,
                episode_title = excluded.episode_title,
                season_number = excluded.season_number,
                episode_number = excluded.episode_number,
                air_datetime = excluded.air_datetime,
                duration = excluded.duration,
                channel_call_sign = excluded.channel_call_sign,
                channel_network = excluded.channel_network,
                qualifiers = excluded.qualifiers,
                is_new = excluded.is_new,
                is_primetime = excluded.is_primetime,
                is_premiere = excluded.is_premiere,
                schedule_state = excluded.schedule_state,
                channel_identifier = COALESCE(excluded.channel_identifier, guide_airings.channel_identifier),
                updated_at = excluded.updated_at
        """, rows)
        # Purge past airings older than 3 hours ago
        cutoff = datetime.now(timezone.utc).isoformat()
        # Normalize both sides with datetime(): raw values are 'YYYY-MM-DDTHH:MM:SSZ' while
        # datetime() returns 'YYYY-MM-DD HH:MM:SS', so a plain string compare never matches same-day rows
        conn.execute("DELETE FROM guide_airings WHERE datetime(air_datetime) < datetime(?, '-3 hours')", (cutoff,))
        conn.commit()


def prune_guide_airings(paths: List[str]) -> int:
    """Remove cached airings the Tablo no longer lists (e.g. dropped from the guide). Returns how many."""
    current = set(paths)
    with get_connection() as conn:
        gone = [r["path"] for r in conn.execute("SELECT path FROM guide_airings") if r["path"] not in current]
        if gone:
            conn.executemany("DELETE FROM guide_airings WHERE path = ?", [(p,) for p in gone])
            conn.commit()
    return len(gone)


def update_airing_schedule_states(states: Dict[str, str]):
    """Set the Tablo record status ('scheduled' / 'none' / ...) for specific airing paths."""
    if not states:
        return
    with get_connection() as conn:
        conn.executemany(
            "UPDATE guide_airings SET schedule_state = ? WHERE path = ?",
            [(state or "none", path) for path, state in states.items()],
        )
        conn.commit()


def get_series_airings(series_paths: List[str]) -> List[Dict[str, Any]]:
    """Future airings of these series, recorded or not (for finding reruns of an episode)."""
    if not series_paths:
        return []
    marks = ",".join("?" * len(series_paths))
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT path, series_path, show_title, episode_title, season_number, episode_number, air_datetime,
                   duration, channel_call_sign, channel_network, schedule_state
            FROM guide_airings
            WHERE series_path IN ({marks}) AND datetime(air_datetime) > datetime('now')
            ORDER BY air_datetime
        """, series_paths).fetchall()
    return [dict(r) for r in rows]


def get_upcoming_recordings(within_hours: Optional[float] = None) -> List[Dict[str, Any]]:
    """Airings the Tablo plans to record that haven't finished yet, soonest first, with show art."""
    query = """
        SELECT ga.path, ga.series_path, ga.show_title, ga.episode_title, ga.season_number, ga.episode_number,
               ga.air_datetime, ga.duration, ga.channel_call_sign, ga.channel_network, ga.qualifiers,
               ga.is_new, ga.is_premiere, g.cover_url, g.backdrop_url, g.schedule_rule
        FROM guide_airings ga
        LEFT JOIN guide_shows g ON g.path = ga.series_path
        WHERE ga.schedule_state = 'scheduled'
          AND datetime(ga.air_datetime, '+' || ga.duration || ' seconds') > datetime('now')
    """
    params: List[Any] = []
    if within_hours is not None:
        query += " AND datetime(ga.air_datetime) < datetime('now', ?)"
        params.append(f"+{float(within_hours)} hours")
    query += " ORDER BY ga.air_datetime ASC, ga.show_title"
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    for r in rows:
        try:
            r["qualifiers"] = json.loads(r["qualifiers"]) if r["qualifiers"] else []
        except ValueError:
            r["qualifiers"] = []
        r["is_new"] = bool(r["is_new"])
        r["is_premiere"] = bool(r["is_premiere"])
    return rows


def get_guide_highlight_counts() -> Dict[str, int]:
    with get_connection() as conn:
        prime_row = conn.execute("""
            SELECT COUNT(DISTINCT series_path) 
            FROM guide_airings 
            WHERE is_new = 1 AND is_primetime = 1 AND series_path != ''
        """).fetchone()
        prem_row = conn.execute("""
            SELECT COUNT(DISTINCT series_path) 
            FROM guide_airings 
            WHERE is_premiere = 1 AND series_path != ''
        """).fetchone()
        return {
            "primetime_new": prime_row[0] if prime_row else 0,
            "premieres": prem_row[0] if prem_row else 0
        }


def get_guide_shows(
    category: Optional[str] = None,
    search: Optional[str] = None,
    rule: Optional[str] = None,
    highlight: Optional[str] = None,
    sort_by: str = "title",
    limit: int = 150,
    offset: int = 0
) -> List[Dict[str, Any]]:
    # One pass over guide_airings for the per-series flags and the next airing,
    # instead of six correlated subqueries per guide show
    query = """
        WITH flags AS (
            SELECT
                series_path,
                MAX(is_new = 1 AND is_primetime = 1) AS has_primetime_new,
                MAX(is_premiere = 1) AS has_premiere
            FROM guide_airings
            GROUP BY series_path
        ),
        next_ga AS (
            SELECT
                series_path, air_datetime, channel_network, channel_call_sign,
                episode_title, season_number, episode_number,
                ROW_NUMBER() OVER (PARTITION BY series_path ORDER BY air_datetime ASC) AS rn
            FROM guide_airings
            -- "Next" airing = the first one that hasn't finished yet (past rows linger ~3h before purge)
            WHERE datetime(air_datetime, '+' || duration || ' seconds') > datetime('now')
        )
        SELECT
            g.*,
            COALESCE(f.has_primetime_new, 0) AS has_primetime_new,
            COALESCE(f.has_premiere, 0) AS has_premiere,
            n.air_datetime AS next_air_datetime,
            n.channel_network AS next_channel_network,
            n.channel_call_sign AS next_channel_call_sign,
            n.episode_title AS next_episode_title,
            n.season_number AS next_season_number,
            n.episode_number AS next_episode_number
        FROM guide_shows g
        LEFT JOIN flags f ON f.series_path = g.path
        LEFT JOIN next_ga n ON n.series_path = g.path AND n.rn = 1
        WHERE 1=1
    """
    params = []

    if highlight == "primetime_new":
        query += " AND f.has_primetime_new = 1"
    elif highlight == "premieres":
        query += " AND f.has_premiere = 1"

    if category and category.lower() != "all":
        query += " AND g.category = ?"
        params.append(category.lower())

    if rule:
        if rule == "scheduled":
            query += " AND g.schedule_rule IN ('new', 'all')"
        elif rule == "unscheduled":
            query += " AND (g.schedule_rule = 'none' OR g.schedule_rule IS NULL)"
        else:
            query += " AND g.schedule_rule = ?"
            params.append(rule)

    # Browsing the guide means "what's airing". Shows with no upcoming airings are only kept when
    # they have a recording rule (series between seasons) and the user is viewing Recording or searching.
    if rule not in ("scheduled", "new", "all"):
        if search and search.strip():
            query += " AND (n.air_datetime IS NOT NULL OR g.schedule_rule IN ('new', 'all'))"
        else:
            query += " AND n.air_datetime IS NOT NULL"

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (g.title LIKE ? OR g.description LIKE ? OR g.genres LIKE ?)"
        params.extend([term, term, term])

    if sort_by == "soonest":
        query += " ORDER BY CASE WHEN next_air_datetime IS NOT NULL THEN 0 ELSE 1 END, next_air_datetime ASC, g.title COLLATE NOCASE ASC"
    elif sort_by == "primetime":
        query += " ORDER BY has_primetime_new DESC, CASE WHEN next_air_datetime IS NOT NULL THEN 0 ELSE 1 END, next_air_datetime ASC, g.title COLLATE NOCASE ASC"
    elif sort_by == "premieres":
        query += " ORDER BY has_premiere DESC, CASE WHEN next_air_datetime IS NOT NULL THEN 0 ELSE 1 END, next_air_datetime ASC, g.title COLLATE NOCASE ASC"
    elif sort_by == "scheduled":
        query += " ORDER BY CASE WHEN g.schedule_rule IN ('new', 'all') THEN 0 ELSE 1 END, g.scheduled_count DESC, g.title COLLATE NOCASE ASC"
    elif sort_by == "airings":
        query += " ORDER BY g.airing_count DESC, g.title COLLATE NOCASE ASC"
    elif sort_by == "recent":
        query += " ORDER BY g.orig_air_date DESC, g.title COLLATE NOCASE ASC"
    else:  # title
        query += " ORDER BY g.title COLLATE NOCASE ASC"

    query += f" LIMIT {int(limit)} OFFSET {int(offset)}"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["genres"] = json.loads(d["genres"]) if d.get("genres") else []
            except Exception:
                d["genres"] = []
            d["has_primetime_new"] = bool(d.get("has_primetime_new"))
            d["has_premiere"] = bool(d.get("has_premiere"))
            if d.get("next_air_datetime"):
                d["next_airing"] = {
                    "datetime": d.get("next_air_datetime"),
                    "network": d.get("next_channel_network"),
                    "call_sign": d.get("next_channel_call_sign"),
                    "title": d.get("next_episode_title"),
                    "season_number": d.get("next_season_number"),
                    "episode_number": d.get("next_episode_number"),
                }
            else:
                d["next_airing"] = None
            result.append(d)
        return result


def get_scheduled_guide_shows() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM guide_shows 
            WHERE schedule_rule IN ('new', 'all')
            ORDER BY title COLLATE NOCASE ASC
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["genres"] = json.loads(d["genres"]) if d.get("genres") else []
            except Exception:
                d["genres"] = []
            result.append(d)
        return result


def get_guide_show_by_path(path: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM guide_shows WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["genres"] = json.loads(d["genres"]) if d.get("genres") else []
        except Exception:
            d["genres"] = []
        return d


def update_guide_show_schedule(path: str, rule: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            UPDATE guide_shows 
            SET schedule_rule = ?, updated_at = ?
            WHERE path = ?
        """, (rule, now, path))
        conn.commit()


def clear_stale_schedule_rules(category: str, scheduled_paths: List[str]) -> int:
    """Mark shows of this category as not recording if the Tablo no longer lists them as scheduled
    (e.g. a rule removed on the TV for a series that is off the air)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT path FROM guide_shows WHERE category = ? AND schedule_rule IN ('new', 'all')", (category,)
        ).fetchall()
        stale = [r["path"] for r in rows if r["path"] not in set(scheduled_paths)]
        if stale:
            conn.executemany("UPDATE guide_shows SET schedule_rule = 'none' WHERE path = ?", [(p,) for p in stale])
            conn.commit()
        return len(stale)


def get_live_airings_for_channels() -> Dict[str, Dict[str, Any]]:
    """Return 'now playing' and 'next up' broadcasts for all channels from the guide cache."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result: Dict[str, Dict[str, Any]] = {}

    with get_connection() as conn:
        # 1. Fetch currently airing programs
        now_rows = conn.execute("""
            SELECT channel_call_sign, channel_network, show_title, episode_title, 
                   season_number, episode_number, air_datetime, duration, qualifiers
            FROM guide_airings
            WHERE datetime(air_datetime) <= datetime(?) 
              AND datetime(air_datetime, '+' || duration || ' seconds') >= datetime(?)
            ORDER BY air_datetime DESC
        """, (now_iso, now_iso)).fetchall()

        for r in now_rows:
            cs = (r["channel_call_sign"] or "").strip()
            if not cs or cs in result:
                continue
            
            # Calculate progress percentage
            start_dt = datetime.fromisoformat(r["air_datetime"].replace("Z", "+00:00"))
            cur_dt = datetime.now(timezone.utc)
            elapsed = (cur_dt - start_dt).total_seconds()
            dur = max(r["duration"] or 1800, 60)
            pct = min(max(int((elapsed / dur) * 100), 0), 100)

            result[cs] = {
                "now": {
                    "title": r["show_title"],
                    "show_title": r["show_title"],
                    "episode_title": r["episode_title"],
                    "season_number": r["season_number"],
                    "episode_number": r["episode_number"],
                    "air_date_time": r["air_datetime"],
                    "air_datetime": r["air_datetime"],
                    "duration": r["duration"],
                    "progress_pct": pct,
                    "progress_percent": pct,
                },
                "next": None
            }

        # 2. Fetch next upcoming programs for each channel
        next_rows = conn.execute("""
            SELECT channel_call_sign, show_title, episode_title, 
                   season_number, episode_number, air_datetime, duration
            FROM guide_airings
            WHERE datetime(air_datetime) > datetime(?)
            ORDER BY air_datetime ASC
        """, (now_iso,)).fetchall()

        for r in next_rows:
            cs = (r["channel_call_sign"] or "").strip()
            if cs in result and result[cs].get("next") is None:
                result[cs]["next"] = {
                    "title": r["show_title"],
                    "show_title": r["show_title"],
                    "episode_title": r["episode_title"],
                    "air_date_time": r["air_datetime"],
                    "air_datetime": r["air_datetime"],
                    "duration": r["duration"]
                }

    return result


def get_epg_schedule(hours: int = 6, start_iso: Optional[str] = None) -> Dict[str, Any]:
    """Fetch structured EPG airings timeline across channels for grid view."""
    if start_iso:
        dt_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    else:
        now = datetime.now(timezone.utc)
        minute = 30 if now.minute >= 30 else 0
        dt_start = now.replace(minute=minute, second=0, microsecond=0)
        # Show from 30 minutes before now to catch beginning of ongoing programs
        dt_start = dt_start - timedelta(minutes=30)

    dt_end = dt_start + timedelta(hours=hours)
    start_str = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = dt_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    slots: List[Dict[str, str]] = []
    curr = dt_start
    while curr < dt_end:
        slots.append({
            "iso": curr.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_str": curr.strftime("%I:%M %p").lstrip("0"),
        })
        curr += timedelta(minutes=30)

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT ga.path, ga.series_path, ga.show_title, ga.episode_title, ga.season_number, ga.episode_number,
                   ga.air_datetime, ga.duration, ga.channel_call_sign, ga.channel_network, ga.qualifiers,
                   ga.is_new, ga.is_primetime, ga.is_premiere, ga.schedule_state, ga.channel_identifier,
                   g.genres AS show_genres, g.category AS show_category
            FROM guide_airings ga
            LEFT JOIN guide_shows g ON g.path = ga.series_path
            WHERE datetime(ga.air_datetime, '+' || ga.duration || ' seconds') > datetime(?)
              AND datetime(ga.air_datetime) < datetime(?)
            ORDER BY ga.air_datetime ASC
        """, (start_str, end_str)).fetchall()

        by_channel: Dict[str, List[Dict[str, Any]]] = {}
        by_identifier: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            cs = (r["channel_call_sign"] or "").strip()
            ident = r["channel_identifier"]
            if not cs and not ident:
                continue
            try:
                genres = json.loads(r["show_genres"]) if r["show_genres"] else []
            except ValueError:
                genres = []

            # Parse qualifiers list safely
            q_list = []
            try:
                if r["qualifiers"]:
                    q_list = json.loads(r["qualifiers"])
            except Exception:
                q_list = []

            item = {
                "path": r["path"],
                "series_path": r["series_path"],
                "title": r["show_title"],
                "show_title": r["show_title"],
                "episode_title": r["episode_title"],
                "season_number": r["season_number"],
                "episode_number": r["episode_number"],
                "air_datetime": r["air_datetime"],
                "duration": r["duration"],
                "is_new": bool(r["is_new"]),
                "is_primetime": bool(r["is_primetime"]),
                "is_premiere": bool(r["is_premiere"]),
                "qualifiers": q_list,
                "schedule_state": r["schedule_state"] or "none",
                "genres": genres,
                "category": r["show_category"] or "",
            }
            if cs:
                by_channel.setdefault(cs, []).append(item)
            if ident:
                by_identifier.setdefault(ident, []).append(item)

    return {
        "window_start": start_str,
        "window_end": end_str,
        "hours": hours,
        "slots": slots,
        "airings_by_channel": by_channel,
        "airings_by_identifier": by_identifier,
    }
