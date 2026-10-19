#!/bin/bash
# Runs TabloView from source on Linux: sets up Python packages the first time, then starts the
# server and opens it in the browser. Stop it with Ctrl+C or by closing the terminal window.
#   bash start-linux.sh             start TabloView (or just open it if it's already running)
#   bash start-linux.sh --install   also add TabloView to the applications menu
# Needs Python 3.12+ (or the "uv" tool, which fetches it) and FFmpeg. See LINUX.md.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
PORT=7070
URL="http://localhost:$PORT"

open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 &
    else echo "Open $URL in your browser."; fi
}

if [ "$1" = "--install" ]; then
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/tabloview.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TabloView
Comment=Recordings, guide and live TV for your Tablo
Exec=bash "$PWD/start-linux.sh"
Icon=$PWD/static/icon-256.png
Terminal=true
Categories=AudioVideo;Video;TV;
EOF
    echo "Added TabloView to your applications menu. Starting it now..."
fi

# Already running: just open it
if command -v curl >/dev/null 2>&1 && curl -s -o /dev/null --max-time 2 "$URL/api/system/info"; then
    echo "TabloView is already running."
    open_browser
    exit 0
fi

PY=""
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Note: FFmpeg isn't installed, so playback in the browser and MP4 export won't work."
    echo "      Install it with your package manager, e.g.  sudo apt install ffmpeg"
    echo
fi

# First run (or one that didn't finish): set up a private Python environment with TabloView's packages
if [ ! -f .venv/.ready ]; then
    echo "First run: setting up TabloView (this takes a minute)..."
    rm -rf .venv
    if [ -n "$PY" ]; then
        if ! "$PY" -m venv .venv 2>/dev/null; then
            rm -rf .venv
            echo "Python can't create TabloView's environment. On Ubuntu, Debian or Mint, install it with:"
            echo "    sudo apt install python3-venv"
            exit 1
        fi
        .venv/bin/python -m pip install --quiet --upgrade pip 2>/dev/null
        .venv/bin/python -m pip install --quiet -r requirements.txt || { echo "Couldn't install TabloView's packages."; exit 1; }
    elif command -v uv >/dev/null 2>&1; then
        # This Linux has an older Python: uv downloads a suitable one just for TabloView
        uv venv --quiet --python 3.12 .venv || exit 1
        uv pip install --quiet --python .venv/bin/python -r requirements.txt || { echo "Couldn't install TabloView's packages."; exit 1; }
    else
        echo "TabloView needs Python 3.12 or newer, and this system has an older one."
        echo "The easiest fix is the free uv tool, which fetches a suitable Python just for TabloView:"
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "Then open a new terminal and run this script again."
        exit 1
    fi
    touch .venv/.ready
fi

echo "TabloView is starting at $URL  (press Ctrl+C to stop)"
( sleep 3 && open_browser ) &
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
