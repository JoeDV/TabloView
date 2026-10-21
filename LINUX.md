# TabloView on Linux

TabloView doesn't have a Linux package yet, but you can run it from its source code on a Linux desktop. This is a test: please tell JoeDV on the Tablo Community Forum how it goes, and which distribution you use.

You need a **Tablo 4th Gen** on the same home network as your computer, and your Tablo account.

## One-time setup

1. **Install FFmpeg** (for playback in the browser and MP4 export) and Python's environment tool. Open a terminal and run the line for your system:

   | System | Command |
   |---|---|
   | Ubuntu 24.04+, Linux Mint 22+, Pop!_OS 24.04+ | `sudo apt install ffmpeg python3-venv` |
   | Fedora | enable [RPM Fusion](https://rpmfusion.org/Configuration), then `sudo dnf install ffmpeg` (Fedora's own `ffmpeg-free` can't convert video for playback) |
   | Arch, Manjaro, EndeavourOS | `sudo pacman -S ffmpeg python` |

2. **Older systems** (Ubuntu 22.04, Debian 12, Linux Mint 21 and similar) have a Python older than the 3.12 TabloView needs. Install the free **uv** tool and TabloView fetches a suitable Python for itself, leaving the system's alone:
   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Then open a new terminal.

3. **Unpack TabloView** somewhere you'll keep it, for example your home folder, so you have a `TabloView` folder.

## Starting TabloView

In a terminal, in the TabloView folder:
```
bash start-linux.sh --install
```
The first time it spends a minute setting itself up, adds **TabloView** to your applications menu, and opens TabloView in your browser at http://localhost:7070. Sign in with your Tablo account; the first sync of your recordings and guide takes about a minute.

- From then on, start it from the applications menu (or `bash start-linux.sh`). Starting it while it's already running just opens it in the browser.
- Keep its terminal window open while you use TabloView. Press **Ctrl+C** or close the window to stop it.

## Good to know

- Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps its sign-in and cache in a `data` folder inside the TabloView folder, and MP4 exports go to its `downloads` folder (choose another under **Device → Storage → Exports**).
- Only this computer can open TabloView; other devices on your network can't.
- Video is converted for the browser by the CPU, or by an NVIDIA graphics card if FFmpeg supports it. On older or low-power computers, set **Device → Playback → Video quality** to *Fastest*.
- Windows-only for now: start with Windows / tray icon and desktop notifications.
- **Open in VLC** downloads a small playlist file; open it with VLC.
- **To update**, see [Updating](#updating) below.
- **To remove it**, delete the TabloView folder and `~/.local/share/applications/tabloview.desktop`.

## Updating

TabloView tells you when a new version is out (**Update available** at the top of the page), with a link to the download.

The simplest way: unzip the new version over your TabloView folder and start it as usual. It notices the new version, sets itself up again (about a minute) and keeps your sign-in and settings.

Prefer to keep each version in its own folder, so you can go back? Keep your data in one place outside them, so every version uses it and you stay signed in. Once, copy your current `data` folder there:
```
mkdir -p ~/.local/share/TabloView
cp -r ~/TabloView/data ~/.local/share/TabloView/
```
(using the folder you unzipped TabloView to), then add this line to `~/.bashrc` (or your shell's startup file):
```
export TABLOVIEW_HOME=~/.local/share/TabloView
```
Open a new terminal, and every version you start uses that data. Exports then go to `~/.local/share/TabloView/downloads` unless you choose a folder under **Device → Storage → Exports**.

`data/config.json` holds your Tablo sign-in; don't share it.

## If something goes wrong

- *"Python can't create TabloView's environment"*: run `sudo apt install python3-venv` and try again.
- *"TabloView needs Python 3.12 or newer"*: install uv (step 2) and try again.
- *Playback doesn't start*: check that `ffmpeg -version` works in a terminal.
- *"This browser can't play TabloView's video"* (Firefox on Fedora, including Kinoite): Fedora's Firefox leaves out the H.264 video codec. Use Chrome or Chromium, use the Firefox Flatpak (it includes the codecs), or add them from RPM Fusion with `sudo dnf install libavcodec-freeworld`. **Open in VLC** works either way.
- *Port already in use*: TabloView or something else is already using port 7070.
- Anything else: copy the text from the terminal window and post it in the forum thread.
