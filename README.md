# Tablo Classic UI (4th Gen Recordings Manager)

A lightning-fast, modern local web application that replaces the Tablo 4th Gen library with the **Classic Legacy Tablo Recordings Interface**.

---

## Features
- **Default Poster Grid:** Clean, responsive grid displaying all recorded Shows, Movies, and Sports currently on your Tablo hard drive.
- **Series Recording Manager ("Scheduled"):** Dedicated management view displaying all series currently configured to record (e.g. *Survivor*, *Jeopardy!*, *NCIS*, etc.), with rule badges (**Record New Only** vs. **Record All Episodes**), upcoming broadcast counts, and one-click buttons to change rules or stop recordings.
- **Broadcast Guide & Show Search:** Real-time search across 590+ over-the-air broadcast TV shows, movies, and sports directly from the Tablo hardware, with instant debounced title/genre filtering and one-click series scheduling.
- **Interactive Guide Series Drawer:** Detailed slide-over panel with high-res cover art, series synopsis, original air date, quick recording rule selector (**Record New**, **Record All**, **Stop Recording**), and live schedule of upcoming broadcast airings with channel logos, call signs (e.g. CBS 29.1 WTTK), and individual episode record/skip toggles.
- **One Image Per Show:** High-contrast badge in the top-right corner showing total recorded episode count and an emerald highlight dot for unwatched episodes.
- **Two-Click Access Episode Drawer:** Clicking any poster immediately opens a slide-over drawer listing all recorded episodes sorted by Season/Episode with one-click actions:
  - **[Watch in Browser]**: HLS.js video player with on-the-fly H.264/AAC transcoding.
  - **[Open in VLC]**: Zero-transcode native playback via instant `.m3u` playlist download.
  - **[Export MP4]**: Background task pulling streams via FFmpeg directly into `./downloads/` folder (`ShowName - SxxExx - Title.mp4`).
  - **[Delete]**: Immediate signed DELETE to the Tablo hardware, decrementing episode counts instantly.
  - **[Delete All Watched]**: One-click cleanup of finished episodes.
  - **Bulk Selection**: Multi-select episodes with bulk delete.
- **Attached Storage Indicator:** Real-time visual capacity bar displaying Free vs. Used GB/TB on your attached USB hard drive (e.g. Seagate Expansion).
- **Fast Local SQLite Cache:** Queries the local database in under 5ms, with an automatic background sync of library recordings and guide items.
- **Built-in API Inspector:** Probes `/server/info`, `/server/harddrives`, `/recordings/airings`, `/recordings/series`, `/guide/series`, and Lighthouse cloud guide.

---

## Architecture
- **Backend:** Python 3.12+ with FastAPI, Uvicorn, HTTPX, SQLite3, and `tablo-api`.
- **Hardware Integration:** Cloud authentication via `lighthousetv.ewscloud.com` followed by HMAC-MD5 signed device requests to the local Tablo on port `8887` and streaming on port `80`.
- **Transcoding & Export:** Local FFmpeg 9.0.1+ integration for live web playback and MP4 downloads.
- **Frontend:** Vanilla CSS & JS single-page application with dark-mode glassmorphism and modern typography (Outfit, Inter, JetBrains Mono).

---

## Quick Start

### 1. Requirements
- Python 3.11+
- FFmpeg (automatically detected in WinGet or system PATH)

### 2. Run the Application

**Option A (1-Click on Windows):**
Double-click [start.bat](file:///c:/Users/Joede/sites/TabloView/start.bat) in File Explorer. It automatically launches the server and opens your web browser.

**Option B (Terminal / PowerShell):**
Open PowerShell in this directory and run:
```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 7070
```

Then open your browser to:
**[http://localhost:7070](http://localhost:7070)**

---

## Credentials & Config
Device information and credentials are automatically saved in `data/config.json` and `.env` (both gitignored).
To test authentication and probe device endpoints from the CLI:
```bash
python test_connection.py
```
