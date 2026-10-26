# TabloView on a Mac

TabloView doesn't have a Mac app yet, but you can run it from its source code. It works on Apple Silicon (M1 and later) and Intel Macs. This is a test: please tell JoeDV on the Tablo Community Forum how it goes.

You need a **Tablo 4th Gen** on the same home network as your Mac, and your Tablo account.

## One-time setup

1. **Install Homebrew** if you don't have it. Open **Terminal** (Applications → Utilities) and paste the command shown on https://brew.sh, then follow its instructions.
2. **Install Python and FFmpeg.** In Terminal:
   ```
   brew install python@3.12 ffmpeg
   ```
3. **Unzip TabloView** somewhere you'll keep it, for example your home folder, so you have a `TabloView` folder.

## Starting TabloView

In Terminal, type `bash ` (with a space after it), drag the **start-mac.sh** file from the TabloView folder into the Terminal window, and press Return.

The first time, it spends a minute setting itself up. Then TabloView opens in your browser at http://localhost:7070. Sign in with your Tablo account; the first sync of your recordings and guide takes a minute or two.

- If macOS asks whether to allow **Terminal** or **Python** to find devices on your local network, click **Allow**. Otherwise TabloView can't reach your Tablo.
- Keep the Terminal window open while you use TabloView. Press **Ctrl+C** or close the window to stop it.
- Next time, start it the same way. It skips the setup.

## Good to know

- Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps its sign-in and cache in a `data` folder inside the TabloView folder, and MP4 exports go to its `downloads` folder (choose another under **Device → Storage → Exports**).
- At first only your Mac can open TabloView. To use it on other devices at home (a phone, a tablet, a TV's browser), turn on **Device → Desktop & network → Allow other devices on my network**, set a PIN, then stop TabloView (**Stop TabloView** on that page, or Ctrl+C) and run start-mac.sh again. The same page shows the address to open on the other devices. If macOS asks whether Python may accept incoming network connections, click **Allow**.
- **Open in VLC** downloads a small playlist file; open it with VLC (https://www.videolan.org) or IINA.
- **To update**, see [Updating](#updating) below.
- **To remove it**, delete the TabloView folder. Python and FFmpeg can be removed with `brew uninstall python@3.12 ffmpeg`.

## Updating

TabloView tells you when a new version is out (**Update available** at the top of the page), with a link to the download.

The simplest way: unzip the new version over your TabloView folder and start it as usual. It notices the new version, sets itself up again (about a minute) and keeps your sign-in and settings.

Prefer to keep each version in its own folder, so you can go back? Keep your data in one place outside them, so every version uses it and you stay signed in. Once, copy your current `data` folder there:
```
mkdir -p ~/Library/Application\ Support/TabloView
cp -r ~/TabloView/data ~/Library/Application\ Support/TabloView/
```
(using the folder you unzipped TabloView to), then add this line to `~/.zshrc`:
```
export TABLOVIEW_HOME=~/Library/Application\ Support/TabloView
```
Open a new terminal, and every version you start uses that data. Exports then go to `~/Library/Application Support/TabloView/downloads` unless you choose a folder under **Device → Storage → Exports**.

`data/config.json` holds your Tablo sign-in; don't share it.

## If something goes wrong

- *"TabloView needs Python 3.12 or newer"*: run `brew install python@3.12` and try again.
- *"No module named uvicorn"*: the first-time setup didn't finish. Delete the `.venv` folder inside the TabloView folder (in Terminal: `rm -rf ~/TabloView/.venv`) and start TabloView again; it sets itself up from scratch. If it stops with *"Couldn't install TabloView's packages"*, the lines above that say why.
- *SSL or CERTIFICATE_VERIFY_FAILED errors during setup* (Python from python.org rather than Homebrew): open Applications → Python 3.x, double-click **Install Certificates.command**, then start TabloView again.
- *Port already in use*: TabloView is probably already running in another Terminal window.
- Anything else: copy the text from the Terminal window and post it in the forum thread.
