# TabloView

A fast desktop interface for the **Tablo 4th Gen** DVR: browse and play recordings, search the guide, schedule series, and watch live TV in your browser.

## Install (Windows)

1. Get **TabloView for TabloTV** from the [Microsoft Store](https://apps.microsoft.com/detail/9NCWVSC7KX2N) (updates automatically), or download **`TabloView-Setup-<version>.exe`** and run it. No admin rights are needed; it installs just for your Windows account.
   - Windows may say *"Windows protected your PC"* because the installer isn't code-signed. Click **More info → Run anyway**.
2. TabloView opens in your browser. **Sign in with your own Tablo account**; TabloView finds the Tablo on your home network.
3. While it runs, TabloView has an icon in the system tray (bottom-right, near the clock). Right-click it to reopen the app, open your downloads folder, or quit. To have it start quietly in the tray when you sign in, turn on **Device → Desktop app → Start TabloView when I sign in to Windows**.

Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps the device access it receives in `%LOCALAPPDATA%\TabloView`, along with its settings and cache. MP4 exports are saved to `Downloads\TabloView`.

To uninstall, use **Settings → Apps → Installed apps → TabloView**. Your sign-in and cache stay in `%LOCALAPPDATA%\TabloView`; delete that folder to remove them too.

### Mac

There's no Mac app yet; Mac users can run it from source with `start-mac.sh`. See [MAC.md](MAC.md).

### Linux

There's no Linux package yet; on a Linux desktop it runs from source with `start-linux.sh`, which can also add it to the applications menu. See [LINUX.md](LINUX.md).

### Using it from a phone or another PC

By default only the computer running TabloView can open it. To allow other devices on your home network, go to **Device → Network access** and choose a PIN; other devices sign in with it once (the PC itself never asks). If Windows asks about the firewall, allow **Private networks** only. Leave it off on shared Wi-Fi.

## Features

- **Home**: continue watching, what's on now on your channels, recent recordings, what's recording in the next 48 hours, season premieres, and new primetime episodes.
- **Library and show pages**: episode thumbnails, play in the browser (resume, timeline with preview frames, closed captions, sleep timer, auto-play next episode, keyboard shortcuts), skip commercials (found in the background for the shows you choose), open in VLC, export to MP4 (smaller H.264, or the original; several at once), delete one, several, or all watched episodes. Protect recordings, set how many recordings of a show your Tablo keeps, or delete watched ones automatically after a few days. Short or failed recordings are tagged, and recorded again from a rerun when there is one.
- **Guide**: search everything airing on your channels; record a series (new or all episodes) or single airings.
- **Live TV**: channel grid for local and streaming channels with recording badges, a Favorites filter, and a warning before live TV takes a tuner a recording needs. Pause and rewind up to 30 minutes, and change channels from the player (C, Page Up / Page Down).
- **Scheduled**: every series your Tablo records, upcoming recordings with Skip, and conflict warnings with a one-click fix (record another airing of the same episode).
- **Device**: sync settings, playback quality (graphics-chip encoding, optional 60 fps), space used by each show with one-click cleanup, version history, and (in the installed app) start with Windows and notifications for recording problems and conflicts.

## Running from source (developers)

Requires Python 3.12 and FFmpeg (`winget install Gyan.FFmpeg.Essentials`).

```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 7070
```

Open http://localhost:7070. From source, data stays in the project folder (`data/`, `transcode/`, `downloads/`), and `TABLO_EMAIL` / `TABLO_PASSWORD` in `.env` are honoured. The previous interface is still available at `/static/legacy/index.html`.

## Testing

```powershell
powershell -ExecutionPolicy Bypass -File tests\run-tests.ps1
```

- **Unit tests** (`tests/unit`, Python `unittest`): conflict math, Live TV categories, update checks, database logic and the API's security guard. They run against a throwaway data folder and never contact a Tablo. The installer build runs them first and stops if any fail.
- **Browser tests** (`tests/ui`, Node + headless Chrome/Edge): every page, bulk delete, record menu, Live TV tuner warnings, upcoming recordings and conflicts, playback, and resume. They need TabloView running and signed in, and adapt to whatever is on your Tablo. Every change (deletes, recording rules, skips, progress, live tuning) is faked inside the test browser; the only real requests are page loads and playing a recording. Run a single suite with `node tests/ui/run.mjs resume`.

## Building the installer

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This creates an isolated `.build-venv`, runs the unit tests, bundles the app with PyInstaller (`packaging/tabloview.spec`) together with your installed FFmpeg, and compiles `dist\TabloView-Setup-<version>.exe` with Inno Setup 6 (`winget install JRSoftware.InnoSetup`). The script refuses to package any local credentials or caches. Bump `APP_VERSION` in `app/config.py` for a new release.

### Microsoft Store package

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1             # dist\TabloView-<version>.msix
powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1 -LocalTest  # install a test copy on this PC
```

Run `build.ps1` first; this wraps its `dist\TabloView` folder in an MSIX using `packaging/msix/AppxManifest.xml` (identity from Partner Center → Product identity). `makeappx` is downloaded once from Microsoft's Windows SDK BuildTools NuGet package into `.build-tools`. The package is uploaded unsigned and the Store signs it. `-LocalTest` registers the unpacked package under a separate test publisher and needs Windows Developer Mode; remove it with `Get-AppxPackage JoeDelVecchio.TabloViewforTabloTV | Remove-AppxPackage`.

A Store install skips the update check (the Store updates it) and says so under **Device → About**.

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
