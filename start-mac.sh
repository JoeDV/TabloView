#!/bin/bash
# Runs TabloView from source on a Mac: sets up Python packages the first time, then starts the
# server and opens it in the browser. Stop it with Ctrl+C or by closing the Terminal window.
#   bash start-mac.sh
# Needs Python 3.12+ and FFmpeg:  brew install python@3.12 ffmpeg
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "TabloView needs Python 3.12 or newer. Install it with:  brew install python@3.12"
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Note: FFmpeg isn't installed, so playback in the browser and MP4 export won't work."
    echo "      Install it with:  brew install ffmpeg"
    echo
fi

# First run (or one that didn't finish): set up a private Python environment with TabloView's packages.
# Only marked ready once the install worked; a half-made one used to be kept, and every start after
# that failed with "No module named uvicorn".
if [ ! -f .venv/.ready ]; then
    echo "First run: setting up TabloView (this takes a minute)..."
    rm -rf .venv
    "$PY" -m venv .venv || exit 1
    .venv/bin/python -m pip install --quiet --upgrade pip
    if ! .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt; then
        echo
        echo "Couldn't install TabloView's packages (the messages above say why)."
        echo "If they mention SSL or CERTIFICATE_VERIFY_FAILED: open Applications > Python 3.x and"
        echo "double-click 'Install Certificates.command', then run this again."
        rm -rf .venv
        exit 1
    fi
    touch .venv/.ready
fi

PORT=7070
echo "TabloView is starting at http://localhost:$PORT  (press Ctrl+C to stop)"
( sleep 3 && open "http://localhost:$PORT" ) &
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
