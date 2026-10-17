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

- Your password goes only to Tablo's sign-in service and is never saved. TabloView keeps its sign-in and cache in a `data` folder inside the TabloView folder, and MP4 exports go to its `downloads` folder.
- Only your Mac can open TabloView; other devices on your network can't.
- **Open in VLC** downloads a small playlist file; open it with VLC (https://www.videolan.org) or IINA.
- **To update**, replace the TabloView folder with a new copy, keeping the `data` folder if you don't want to sign in again.
- **To remove it**, delete the TabloView folder. Python and FFmpeg can be removed with `brew uninstall python@3.12 ffmpeg`.

## If something goes wrong

- *"TabloView needs Python 3.12 or newer"*: run `brew install python@3.12` and try again.
- *Port already in use*: TabloView is probably already running in another Terminal window.
- Anything else: copy the text from the Terminal window and post it in the forum thread.
