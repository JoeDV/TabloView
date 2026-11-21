# TabloView in Docker

For a home server that's always on (Ubuntu, Debian, Unraid, a NAS that runs containers). This is new and hasn't been tried by many people yet: please tell JoeDV on the Tablo Community Forum how it goes.

You need a **Tablo 4th Gen** on the same home network as the server, and your Tablo account.

## Before you start

- **Linux only.** TabloView needs *host networking*, so it can find your Tablo and so Roku Media Player, VLC and other players can find it. Docker Desktop on Windows or a Mac doesn't fully support that; there, use the regular Windows or Mac download.
- **Converting video uses the CPU.** Antenna channels come from the Tablo as MPEG-2, and TabloView converts them for browsers, phones, Roku and MP4 exports. One channel needs roughly one modern CPU core; a small NAS or a Raspberry Pi may manage one channel but not two. Plex, Jellyfin, Emby and Channels DVR take the picture unconverted, so they need very little.

## Setting it up

1. Download TabloView's source (the Linux download on GitHub, or `git clone https://github.com/JoeDV/TabloView`) onto the server.
2. In its folder, open `docker-compose.yml` and fill in:
   - `TABLO_EMAIL` and `TABLO_PASSWORD`: your Tablo account. TabloView signs in with them the first time, and doesn't save the password.
   - `TABLO_DEVICE`, only if your account has more than one Tablo: its name (as in Tablo's app) or its ID.
   - `TABLOVIEW_PIN`: the PIN your devices enter, 4 to 6 digits.
   - `TABLOVIEW_ADMIN`: your own computer's address, such as `192.168.1.50` (see below).
   - `TZ`: your time zone, such as `America/Chicago`.
3. Start it:
   ```
   docker compose up -d --build
   ```
4. Open `http://<server address>:7070` in a browser on your home network and enter the PIN. The first sync of your recordings and guide takes about a minute.

Once it's signed in you can delete the `TABLO_EMAIL` and `TABLO_PASSWORD` lines; the sign-in is kept in `tabloview-data`.

## Settings only "this PC" can change

Some settings can only be changed on the computer TabloView runs on: network access and the PIN, sharing the Tablo with Plex and other apps, playlist addresses and where exports go. A server has no screen, so list the devices that may change them in `TABLOVIEW_ADMIN`:

```
TABLOVIEW_ADMIN: "192.168.1.50"                  # one computer
TABLOVIEW_ADMIN: "192.168.1.50, 192.168.1.51"    # several
```

Those devices are treated like the server itself: they also don't need the PIN. Only home-network addresses count; a Tailscale or internet address never does, whatever the list says. Give your computer a fixed address in your router (DHCP reservation) so the list stays right.

## Your files

| In the container | On the server (as in docker-compose.yml) | What |
|---|---|---|
| `/data` | `./tabloview-data` | Settings, sign-in, guide cache, logs |
| `/data/downloads` | `./exports` | MP4 exports |

Back up `tabloview-data` to keep your settings. Removing the container doesn't touch either folder.

## Plex, Jellyfin, Emby, Channels DVR and Roku

Turn on **Settings → Live TV → Share your antenna channels with other apps** from a device in `TABLOVIEW_ADMIN`. Settings shows the addresses to give each app (port 5004). Roku Media Player, VLC, Kodi and smart TVs find **TabloView** on the network by themselves.

## Using the graphics chip (optional)

TabloView tries Intel Quick Sync, NVIDIA's encoder and VAAPI before the CPU, and uses whichever works.

- **Intel:** uncomment the `devices: - /dev/dri:/dev/dri` lines in `docker-compose.yml`. The image includes Intel's video drivers, so TabloView uses Quick Sync on newer chips (Tiger Lake and later) and VAAPI on older ones (from about 2015 on). If neither works, it falls back to the CPU on its own. If the server has more than one graphics chip, set `TABLOVIEW_VAAPI_DEVICE` to the right one (such as `/dev/dri/renderD129`).
- **NVIDIA:** install the NVIDIA Container Toolkit on the server and give the container the GPU (`gpus: all` under the service, or `runtime: nvidia`).

**Settings → Playback** says what TabloView is converting with.

## Updating

```
git pull                       # or unpack the new download over the folder
docker compose up -d --build
```

Your settings and exports stay where they are.

## Everything you can set

| Variable | What it does |
|---|---|
| `TABLO_EMAIL`, `TABLO_PASSWORD` | Sign in to your Tablo account at start, if not signed in yet |
| `TABLO_DEVICE` | Which Tablo, by name or ID, when the account has several |
| `TABLOVIEW_NETWORK=1` | Let other devices at home use TabloView (Settings → Desktop & network) |
| `TABLOVIEW_PIN` | The PIN other devices enter (4 to 6 digits). Changing it signs every device out |
| `TABLOVIEW_ADMIN` | Home devices treated like the server itself (addresses or ranges, comma-separated) |
| `TZ` | Your time zone |
| `TABLOVIEW_VAAPI_DEVICE` | Which graphics chip VAAPI uses (default `/dev/dri/renderD128`) |
