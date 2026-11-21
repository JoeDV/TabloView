# TabloView in a container, for a home server (see DOCKER.md). Runs from source, as on Linux.
#   docker compose up -d        with docker-compose.yml beside this file
# Needs host networking: TabloView finds the Tablo, and players find TabloView, on the home network.
FROM python:3.12-slim-trixie

# FFmpeg converts the picture for browsers, phones and Roku, and makes the MP4 exports.
# Intel graphics (with /dev/dri passed in, see DOCKER.md): the VA drivers for VAAPI, the non-free one
# because the free one encodes H.264 only in low-power mode, which needs firmware most hosts don't
# load (a Comet Lake user, 2026-11-21); i965 for older chips; Intel's VPL runtime for Quick Sync on
# Tiger Lake and newer. Intel's packages exist only for amd64.
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && if [ "$(dpkg --print-architecture)" = amd64 ]; then \
      apt-get install -y --no-install-recommends intel-media-va-driver-non-free i965-va-driver libmfx-gen1.2; \
    fi \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# Settings, sign-in, cache and exports (exports in /data/downloads unless another folder is chosen)
ENV TABLOVIEW_HOME=/data \
    PYTHONUNBUFFERED=1
VOLUME /data

# 7070: TabloView. 5004: the tuner for Plex, Jellyfin, Emby and Channels DVR (when turned on).
# DLNA (Roku Media Player, VLC...) also uses UDP 1900.
EXPOSE 7070 5004

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7070/api/system/info', timeout=4)" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7070"]
