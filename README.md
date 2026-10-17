# TabloView

A fast desktop interface for the **Tablo 4th Gen** DVR: browse and play recordings, search the guide, schedule series, and watch live TV in your browser.

## Install (Windows)

1. Download **`TabloView-Setup-<version>.exe`** and run it. No admin rights are needed; it installs just for your Windows account.
   - Windows may say *"Windows protected your PC"* because the installer isn't code-signed. Click **More info → Run anyway**.
2. TabloView opens in your browser. **Sign in with your own Tablo account**; TabloView finds the Tablo on your home network.
3. While it runs, TabloView has an icon in the system tray (bottom-right, near the clock). Right-click it to reopen the app, open your downloads folder, or quit.

Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps the device access it receives in `%LOCALAPPDATA%\TabloView`, along with its settings and cache. MP4 exports are saved to `Downloads\TabloView`.

To uninstall, use **Settings → Apps → Installed apps → TabloView**. Your sign-in and cache stay in `%LOCALAPPDATA%\TabloView`; delete that folder to remove them too.

### Using it from a phone or another PC

By default only the computer running TabloView can open it. To allow other devices on your home network, go to **Device → Network access**. If Windows asks about the firewall, allow **Private networks** only. Anyone on that network can then control your Tablo, so leave it off on shared Wi-Fi.

## Features

- **Home**: recent recordings, what's recording in the next 48 hours, season premieres, and new primetime episodes.
- **Library and show pages**: play in the browser, open in VLC, export to MP4, delete one, several, or all watched episodes.
- **Guide**: search everything airing on your channels; record a series (new or all episodes) or single airings.
- **Live TV**: channel grid for local and streaming channels, with one-click tuning.
- **Scheduled**: every series your Tablo records, with quick rule changes.

## Running from source (developers)

Requires Python 3.12 and FFmpeg (`winget install Gyan.FFmpeg.Essentials`).

```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 7070
```

Open http://localhost:7070. From source, data stays in the project folder (`data/`, `transcode/`, `downloads/`), and `TABLO_EMAIL` / `TABLO_PASSWORD` in `.env` are honoured. The previous interface is still available at `/static/legacy/index.html`.

## Building the installer

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This creates an isolated `.build-venv`, bundles the app with PyInstaller (`packaging/tabloview.spec`) together with your installed FFmpeg, and compiles `dist\TabloView-Setup-<version>.exe` with Inno Setup 6 (`winget install JRSoftware.InnoSetup`). The script refuses to package any local credentials or caches. Bump `APP_VERSION` in `app/config.py` for a new release.

## Architecture

- **Backend**: FastAPI + Uvicorn, SQLite cache, `tablo-api` for Tablo cloud sign-in and HMAC-signed requests to the local device.
- **Playback**: FFmpeg transcodes to H.264/AAC HLS for the browser (hls.js); exports copy the video stream into MP4.
- **Frontend**: dependency-free single-page app in `static/`.
- **Desktop app**: `tabloview.py` runs the server, opens the browser and provides the tray icon. State-changing API calls require an `X-TabloView` header and a local Host, so other websites can't drive the API.

## License and third-party software

TabloView is licensed under the GPL-3.0 (see `LICENSE`). The installer bundles:

- **FFmpeg** (GPL), built by gyan.dev; its license is included next to `ffmpeg.exe`. Source: https://ffmpeg.org and https://www.gyan.dev/ffmpeg/builds/
- **hls.js** (Apache-2.0), in `static/vendor/`.
- Python and its libraries, via PyInstaller.
