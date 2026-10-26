# TabloView

A fast desktop app for the **Tablo 4th Gen** over-the-air DVR: browse and play your recordings, skip commercials, search the guide, schedule series, and watch live TV, two channels at once if you like, in your browser.

Older Tablos that have Tablo's update for the new Tablo app are reported to work too.

> TabloView is an independent, unofficial project. It isn't made by, affiliated with, or endorsed by Tablo or its owners. "Tablo" is their trademark.

## Install

### Windows

1. Get **TabloView for TabloTV** from the [Microsoft Store](https://apps.microsoft.com/detail/9NCWVSC7KX2N) (it updates automatically), or download **`TabloView-Setup-<version>.exe`** from the [latest release](https://github.com/JoeDV/TabloView/releases/latest) and run it. No admin rights are needed; it installs just for your Windows account.
   - The installer isn't code-signed, so Windows may say *"Windows protected your PC"*. Click **More info → Run anyway**. (The Store version doesn't have this.)
2. TabloView opens in your browser. **Sign in with your own Tablo account**; TabloView finds the Tablo on your home network.
3. While it runs, TabloView has an icon in the system tray (bottom-right, near the clock). Right-click it to reopen the app, open your downloads folder, check for updates, or quit. To have it start quietly in the tray when you sign in to Windows, turn on **Device → Desktop app → Start TabloView when I sign in to Windows**.

Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps the device access it receives, its settings and its cache in `%LOCALAPPDATA%\TabloView`. MP4 exports are saved to `Downloads\TabloView`.

To uninstall, use **Settings → Apps → Installed apps → TabloView**. The installer version leaves its sign-in and cache in `%LOCALAPPDATA%\TabloView`; delete that folder to remove them too.

### Mac and Linux

There's no Mac or Linux package yet, but TabloView runs from its source code with a start script that sets everything up. Download **`TabloView-<version>-mac.zip`** or **`TabloView-<version>-linux.tar.gz`** from the [latest release](https://github.com/JoeDV/TabloView/releases/latest) (or clone this repository) and follow [MAC.md](MAC.md) or [LINUX.md](LINUX.md).

### Using it from a phone or another computer

By default only the computer running TabloView can open it. To allow other devices on your home network, turn on **Device → Network access** and choose a PIN; other devices sign in with it once (the computer running TabloView never asks). If Windows asks about the firewall, allow **Private networks** only. Leave it off on shared Wi-Fi.

## Features

- **Home**: continue watching, what's on now on your channels, shows you've recorded before that are back for a new season, recent recordings, what's recording in the next 48 hours, season premieres and new primetime episodes.
- **Recordings**: episode thumbnails; play in the browser with resume, a timeline with preview frames, closed captions, a sleep timer, auto-play of the next episode and keyboard shortcuts (press **?** in the player). **Skip commercials** for the shows you choose: TabloView finds the breaks in the background on your computer and marks them on the timeline. Open in VLC, export to MP4 (smaller H.264 or the original video; several at once), delete one, several or all watched episodes, protect recordings, set how many recordings of a show your Tablo keeps, or delete watched ones automatically. Recordings that fail or come out short are tagged and recorded again from a rerun when there is one.
- **Guide**: search everything airing on your channels; record a series (new or all episodes) or single airings.
- **Live TV**: a channel grid for antenna and streaming channels with recording badges and a Favorites filter, and a warning before live TV takes a tuner a recording needs. Pause and rewind up to 30 minutes, change channels from the player, and **watch two channels at once**: a live channel next to live TV or a recording, side by side, big and small, or flipping between them.
- **Scheduled**: every series your Tablo records, upcoming recordings with Skip, conflict warnings with a one-click fix (record another airing of the same episode), and Add to calendar (Google, Outlook, Apple).
- **Device**: sync settings, playback quality (graphics-chip encoding, optional 60 fps), space used by each show with one-click cleanup, signal health (which channels' recordings fail, why and when), a PIN for other devices, version history, and (in the Windows app) start with Windows and notifications for recording problems and conflicts.

## Privacy

TabloView collects nothing and sends nothing to the developer; everything stays on your computer and your Tablo. See [PRIVACY.md](PRIVACY.md).

## Help and feedback

Questions, bug reports and ideas: find the TabloView thread on the [Tablo Community Forum](https://community.tablotv.com/) or message **JoeDV** there. Issues and pull requests here are welcome too.

## Running from source (developers)

Requires Python 3.12+ and FFmpeg (Windows: `winget install Gyan.FFmpeg.Essentials`).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 7070
```

Open http://localhost:7070. (On Windows, `start.ps1` does the last two steps; on Mac and Linux use `start-mac.sh` / `start-linux.sh`.) From source, data stays in the project folder (`data/`, `transcode/`, `downloads/`). For development you can put `TABLO_EMAIL` / `TABLO_PASSWORD` in a `.env` file (see `.env.example`); it's never committed, but it is stored in plain text, so only do this on your own machine.

`tabloview.py` is the desktop launcher used by the Windows app: it starts the server, opens the browser and provides the tray icon (it needs `pystray` and `pillow`).

## Testing

```powershell
powershell -ExecutionPolicy Bypass -File tests\run-tests.ps1
```

- **Unit tests** (`tests/unit`, Python `unittest`): conflicts, commercial detection, cleanup and re-recording rules, the guide sync, the PIN, update checks, database logic and the API's security guard. They run against a throwaway data folder and never contact a Tablo. The installer build runs them first and stops if any fail.
- **Browser tests** (`tests/ui`, Node + headless Chrome or Edge): every page and most features, against a running TabloView that's signed in (default http://localhost:7070; set `TABLOVIEW_URL` for another address). They adapt to whatever is on your Tablo, and every change (deletes, recording rules, skips, progress, settings) is faked inside the test browser; the only real requests are page loads and playing recordings. Live TV is tuned for real only when `TABLOVIEW_ALLOW_TUNE=1` is set. Run one suite with `node tests/ui/run.mjs controls`.

## Building

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This creates an isolated `.build-venv`, runs the unit tests, bundles the app with PyInstaller (`packaging/tabloview.spec`) together with your installed FFmpeg, and compiles `dist\TabloView-Setup-<version>.exe` with Inno Setup 6 (`winget install JRSoftware.InnoSetup`). It refuses to package local credentials or caches. Bump `APP_VERSION` in `app/config.py` for a new release.

### Microsoft Store package

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1             # dist\TabloView-<version>.msix
powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1 -LocalTest  # install a test copy on this PC
```

Run `build.ps1` first; this wraps its `dist\TabloView` folder in an MSIX using `packaging/msix/AppxManifest.xml`. `makeappx` is downloaded once from Microsoft's Windows SDK BuildTools NuGet package into `.build-tools`. The package is uploaded unsigned and the Store signs it. `-LocalTest` registers the unpacked package under a separate test publisher and needs Windows Developer Mode; remove it with `Get-AppxPackage JoeDelVecchio.TabloViewforTabloTV | Where-Object Publisher -eq 'CN=TabloView Local Test' | Remove-AppxPackage`.

Store copies get updates from the Store; TabloView asks the Store whether one is waiting and says so in the sidebar.

## Architecture

- **Backend**: FastAPI + Uvicorn with a SQLite cache, and `tablo-api` for Tablo sign-in and HMAC-signed requests to the local device. Syncs fetch objects 50 at a time (`POST /batch`): the Tablo refuses connections for about a minute after a burst of single requests.
- **Playback**: FFmpeg converts to H.264/AAC HLS for the browser (hls.js), on the graphics chip when it can (Quick Sync, NVENC or AMF) and on the CPU otherwise. Broadcast captions travel inside the converted video; timeline previews come from the Tablo's own trick-play files.
- **Commercial detection** (`app/commercials.py`): one low-priority FFmpeg pass per recording finds black frames and compares each second's colours with the show's own look; tuned to skip too little rather than too much.
- **Frontend**: a dependency-free single-page app in `static/`.
- **Security**: state-changing API calls need an `X-TabloView` header and a local or IP Host header, so other websites can't drive the API; other devices on the network need the PIN.

## License and third-party software

TabloView is licensed under the GPL-3.0 (see `LICENSE`). The Windows app bundles:

- **FFmpeg** (GPLv3), the gyan.dev "essentials" build installed when the app is built; its license is included next to `ffmpeg.exe`. The exact version and links to its source (`https://ffmpeg.org/releases/ffmpeg-<version>.tar.xz`) and to the build (`https://github.com/GyanD/codexffmpeg/releases/tag/<version>`) are under Help → About and licenses.
- **hls.js** (Apache-2.0), in `static/vendor/` with its license.
- Python and its libraries, via PyInstaller.
