# The Tablo 4th Gen API, as TabloView uses it

Tablo has never published an API for its 4th Gen DVRs. This page records what TabloView has worked out by using one. It covers how to sign in, the requests TabloView makes, what comes back, and how the device behaves.

It's written for developers building their own tools. Every endpoint here is one TabloView calls, so it has been used against real Tablos. Where a detail is an inference rather than something observed, it says so. Anything not listed is unknown to us.

Builds on [tablo-api](https://github.com/trevor-viljoen/tablo-api) by Trevor Viljoen, which first documented the sign-in and request signing (credited there to the tablo2plex project).

> **Be gentle.** These are people's DVRs, often recording while you test. Only send requests you understand, batch your reads (see [Request limits](#request-limits)), and don't guess at endpoints on someone else's Tablo. Tablo can change any of this in an update.

## Contents

- [How it fits together](#how-it-fits-together)
- [Signing in (cloud)](#signing-in-cloud)
- [Signing local requests](#signing-local-requests)
- [Request limits](#request-limits)
- [Local endpoints](#local-endpoints)
- [Objects](#objects)
- [Watching (streams and tuners)](#watching-streams-and-tuners)
- [Cloud endpoints](#cloud-endpoints)
- [Unknown](#unknown)

## How it fits together

| Part | Address | Used for |
|---|---|---|
| Tablo cloud ("Lighthouse") | `https://lighthousetv.ewscloud.com` | Signing in, finding your Tablos, the channel lineup, the streaming (FAST) channel guide |
| The Tablo itself | `http://<tablo-ip>:8887`, from the sign-in's device list | Everything else: recordings, the antenna guide, recording rules, tuners, streams, storage |

The local API is plain HTTP on your network, but every request except `/ping` and images must be signed. Once signed in, the local side keeps working when the cloud is down: recordings, antenna TV and the schedule all still work.

## Signing in (cloud)

All cloud calls send a mobile-app `User-Agent` (tablo-api uses `Tablo-FAST/2.0.0 (Mobile; iPhone; iOS 16.6)`).

1. **`POST /api/v2/login/`** with `{"email": "...", "password": "..."}` returns an access token. Its exact shape is in tablo-api's `_LoginResponse`.
2. **`GET /api/v2/account/`** with the login's `Authorization` header returns the account's profiles and devices. Each device has a `serverId`, a `name` and a `url`, which is the Tablo's local address.
3. **`POST /api/v2/account/select/`** with `{"pid": "<profile identifier>", "sid": "<serverId>"}` returns a token for that Tablo, called the *Lighthouse token*.

Keep three things for later: the access token, the Lighthouse token, and the device's local URL. TabloView never stores the password; it signs in again only when the tokens stop working. The Tablo only accepts signed local requests after the account has signed in through the cloud. Before that, it answers 401.

## Signing local requests

Each local request carries two headers:

```
Date: <RFC 1123 date in GMT, e.g. Tue, 21 Oct 2026 18:04:05 GMT>
Authorization: tablo:<device key>:<signature>
```

`signature` is an HMAC-MD5, hex encoded, keyed with the app's hash key, of:

```
<METHOD>\n<PATH>\n<MD5 hex of the body, or empty>\n<Date header>
```

- The two keys were extracted from Tablo's iOS app. They're in tablo-api's `auth.py` and aren't repeated here.
- **`PATH` is the bare path, without the query string.** Signing `?state=scheduled` as part of the path gets a 401. Send the query in the URL, but leave it out of the signature.
- Sign just before sending. A request that waited in a queue with an old `Date` may be refused.
- TabloView sends `User-Agent: Tablo-FAST/1.7.0 (Mobile; iPhone; iOS 18.4)`, and `Content-Type: application/json` when there's a body.
- A 401 means a bad signature or a sign-in the Tablo no longer accepts. Signing in through the cloud again fixes the second.

## The `?lh` switch: streaming channels

Tablo's current app adds `?lh` to every request. It matters: **anything to do with streaming (FAST) channels only exists for requests ending in `?lh`**. Without it, the Tablo answers 404 "not found" for those objects and leaves them out of lists. Antenna objects answer either way. Verified 2026-10-21:

- `GET /recordings/airings?lh` and `/recordings/series?lh` are the plain lists plus streaming recordings (31 → 32 recordings, 8 → 9 series), nothing missing.
- A streaming recording's own requests (`…/watch`, reading its series' `/episodes`) need `?lh`. Antenna recordings accept `?lh` too.
- Streaming guide airings are `/guide/LH-…` objects (the cloud guide's airing ID), and only exist with `?lh`, including inside `/batch?lh`.
- As always, sign the bare path: the `?lh` is not part of the signature.

## Request limits

These are the most important things to know about the Tablo.

- **It answers HTTP/1.0 and closes the connection after every request.** A few thousand requests in a short burst make it **refuse all connections for about 64 seconds** ("connection refused" or timeouts). It's the number of requests that triggers this, not how many are in flight at once.
- **Read objects with `POST /batch`, up to 50 paths per request** (see below). A full library and guide load on a new PC went from 5–10 minutes, with a refusal, to about 25 seconds for 2,811 recordings in 57 requests.
- TabloView keeps at most 4 requests in flight, 2 of them for background syncs, pauses briefly between batches, and waits out a refusal rather than retrying.
- Never loop single `GET`s over many paths.

## Local endpoints

**Verified** means TabloView uses it and has seen the result described. Paths in `{braces}` come from earlier responses; don't build them yourself.

### Device

| Request | Returns | Notes |
|---|---|---|
| `GET /ping` | `{"sid": ...}` | The only unsigned request. Verified. |
| `GET /server/info` | Device details | `server_id`, `name`, `version` (firmware, e.g. `2.2.58`), `build_number`, `local_address`, `setup_completed`, `availability` (`ready`), and `model`: `name` (e.g. "Tablo 4G QUAD 128GB"), `type` (`t4g4`), `wifi`, and `tuners`, the number of antenna tuners. `timezone` is empty and marked `deprecated`. Verified. |
| `GET /server/network` | How the Tablo is connected | `ip`, `connection` (`ethernet` on a wired Tablo; presumably `wifi` otherwise), `status` (`online`), `server_id`. Verified on a wired Tablo; what it adds on Wi-Fi (perhaps a signal strength) isn't known yet. TabloView shows it under Device → Desktop & network. |
| `GET /server/tuners` | A list of tuner slots | Each slot has `in_use`, `recording`, `channel` (a `/guide/channels/{id}` path) and `channel_identifier` (as in the channel lineup). A 4-tuner Tablo lists **8** slots: the first 4 are antenna tuners, the rest are virtual slots used by streaming (FAST) channels (verified by tuning one of each). |
| `GET /server/harddrives` | A list of drives | `name` (e.g. "Internal Flash (128 GB)"), `kind` (`internal`), `connected`, `busy_state`, `format_state`, `error`, and `size`, `usage`, `free` and `limit` in bytes (also as `*_mib`). Verified. |
| `GET /images/{image_id}` | JPEG | Unsigned. IDs come from objects (e.g. `snapshot_image.image_id`). Verified. |
| `GET /server/guide/status?lh` | The Tablo's guide | `guide_seeded`, `last_update` (when it last downloaded the guide), `limit` (how far ahead it reaches, about 2 weeks) and `download_progress` (`null` when idle). Verified. |
| `POST /server/guide/refresh?lh` (no body) | Starts a guide download | What the Tablo app's **Update guide** button sends (captured 2026-10-22). On a QUAD, `last_update` moved on about a minute later. Verified. |

### Reading many objects

| Request | Body | Returns |
|---|---|---|
| `POST /batch` | A JSON list of up to 50 object paths | `{ "<path>": <object>, ... }`. Paths that fail to resolve are missing, or not objects. Verified. |

Every list endpoint returns **paths**, not objects. Read the objects through `/batch`.

### Recordings

| Request | Returns / does |
|---|---|
| `GET /recordings/airings` | Paths of every recording |
| `GET /recordings/series` | Paths of recorded series (with art and the keep rule) |
| `GET /recordings/shows`, `/recordings/movies`, `/recordings/sports` | Paths of the other kinds of recording. TabloView lists these in its API inspector but builds its Library from airings and series. |
| `PATCH /recordings/series/episodes/{id}` with `{"position": <seconds>}` | Saves the resume point. **This also marks it unwatched.** |
| `PATCH` the same path with `{"watched": true}`, or `{"watched": false, "position": 0}` | Marks it watched, or unwatched from the start |
| `PATCH` the same path with `{"protected": true \| false}` | Protects it from automatic deletion |
| `DELETE` the same path | Deletes the recording. 200 or 204 = deleted; 404 = already gone. |
| `PATCH /recordings/series/{id}` with `{"keep": {"rule": "count", "count": N}}`, or `{"keep": {"rule": "none", "count": null}}` | Keeps only the newest N recordings (the Tablo deletes older ones itself), or all. The response echoes `keep`. |

Recording paths look like `/recordings/series/episodes/{id}` (movie and sports recordings may differ); use whatever `/recordings/airings` returns. All of these are verified.

### Antenna guide and recording rules

| Request | Returns / does |
|---|---|
| `GET /guide/channels` | Paths of antenna channels; their objects have `channel` details (call sign, number, network, `channel_identifier`, logos) |
| `GET /guide/series`, `/guide/movies`, `/guide/sports` | Paths of what's in the guide (about 2 weeks). Sports entries are leagues. |
| `GET /guide/series?state=scheduled` (same for movies and sports) | Paths with a recording rule, **including ones with nothing in the guide now** (e.g. between seasons). Remember to sign the bare path. |
| `GET /guide/airings` | Paths of every airing in the guide (thousands: read them with `/batch`) |
| `GET /guide/series/{id}/episodes` | That series' airing paths |
| `GET /guide/sports/{id}/events` | That league's games (sports use `events`, not `episodes`) |
| `GET /guide/movies/{id}/airings` | That movie's airings (`/episodes` is a 404 for movies) |
| `PATCH /guide/series/{id}` with `{"schedule": {"rule": "new" \| "all" \| "none"}}` | Sets the series recording rule. The Tablo re-plans its schedule shortly after: re-read the airings a couple of seconds later to see the result. |
| `PATCH` an airing path, e.g. `/guide/series/episodes/{id}` or `/guide/movies/airings/{id}`, with `{"scheduled": true \| false}` | Records or skips one airing. Also how to record a show already on air (from now on: the recording doesn't go back to the start). |

All verified.

## Objects

Fields TabloView relies on. There are more; inspect a real response.

### Recording (e.g. `/recordings/series/episodes/{id}`)

| Field | Meaning |
|---|---|
| `object_id` | Numeric ID |
| `series_path` | The `/recordings/series/...` it belongs to |
| `airing_details.datetime`, `.duration`, `.show_title`, `.channel.channel` | Scheduled start (UTC), scheduled length in seconds, title, and channel (`call_sign`, `network`, ...) |
| `episode.title`, `.season_number`, `.number`, `.description` | Episode details (`number` is the episode number) |
| `user_info.watched`, `.position`, `.protected` | Watched, resume point in seconds, protected |
| `video_details.state` | `recording`, `finished` or `failed`. **The Tablo won't play a failed recording** (a watch request gets 404). |
| `video_details.duration` | Seconds actually recorded (the scheduled slot plus about 75 s of padding) |
| `video_details.seek` | Where the program starts in the recording. The Tablo starts recording a little early. |
| `video_details.recorded_offsets.end` | Seconds past the scheduled end; negative = stopped early |
| `video_details.clean` | `false` when the Tablo noticed problems in the recording (weak signal) |
| `video_details.error` | Why a recording failed, when it says |
| `snapshot_image.image_id` | A frame from the recording (`/images/{id}`) |

### Recorded series

`title`, art, and `keep` (`{"rule": "count", "count": N}` or `{"rule": "none"}`).

### Guide airing (e.g. `/guide/series/episodes/{id}`)

| Field | Meaning |
|---|---|
| `series_path`; `sport_path` for games; `movie_path` for movies | The series, league or movie |
| `airing_details.datetime`, `.duration`, `.show_title`, `.channel.channel` | As for recordings (`channel_identifier` matches the channel lineup) |
| `episode.*` | As for recordings. Games have `event.title` (e.g. "Philadelphia 76ers at New York Knicks") instead. |
| `qualifiers` | Tags such as `new`, `premiere`, `season_premiere`, `series_premiere`, `primetime` |
| `schedule.state` | `scheduled` (will record), `conflicted` (wants to, but no tuner is free: the first scheduled wins), `skipped`, or `none` |
| `schedule.skip_reason` | Why it's skipped. Seen: `none`, `not_new` (a "Record New" series decided it isn't new). Others likely exist. |

### Guide series

`title`, art, and `schedule.rule` (`new`, `all` or `none`).

## Watching (streams and tuners)

**`POST {path}/watch`** starts a stream. `{path}` is a recording's path, or `/guide/channels/{channel_identifier}` for live TV. The body is the iOS app's (copied from tablo-api):

```json
{"bandwidth": null, "platform": "ios", "device_id": "<a UUID you keep>",
 "extra": {"limitedAdTracking": 1, "deviceOSVersion": "16.6", "lang": "en_US", "height": 1080, "width": 1920,
           "deviceId": "00000000-0000-0000-0000-000000000000", "deviceModel": "iPhone10,1", "deviceMake": "Apple", "deviceOS": "iOS"}}
```

It returns `playlist_url` (an HLS playlist served by the Tablo), `token`, `expires` and `keepalive`.

- **Live TV video:** antenna channels are MPEG-2 at broadcast frame rates. Most browsers can't play that, so TabloView converts it with FFmpeg. Streaming channels are usually H.264 and can pass straight through.
- **End the session when you're done:** `DELETE /player/sessions/{token}`. Otherwise the Tablo keeps the tuner reserved until the session times out, and closing a few channels in a row ties up every tuner. Verified.
- **503 Service Unavailable** on watch means no tuner is free, **or** the Tablo can't pick up that channel right now (weak signal). It doesn't say which; check `/server/tuners`.
- **Failed recordings** return 404 on watch.
- If `{path}/watch` returns 400 or 404, TabloView falls back to `POST /watch` with `{"path": "<path>"}`. That's tablo-api's alternative, kept for safety; we haven't seen a Tablo need it.

## Cloud endpoints

These need `Authorization: Bearer <access token>` plus a `Lighthouse: <Lighthouse token>` header.

| Request | Returns |
|---|---|
| `GET /api/v2/account/{lighthouse token}/guide/channels/` | The full channel lineup: antenna channels (`kind: "ota"`) and streaming channels (`kind: "ott"`), each with `identifier`, `name` and logos (`originalLarge` in color, `lightLarge` white, `darkLarge`). Streaming channels have an `ott` object: `major`, `minor`, `callSign`, `network`, `provider`, `channelPartner`, `streamUrl` (the stream itself, with ad parameters to fill in), and **`canRecord`** (see below). |
| `GET /api/v2/account/{lighthouse token}/guide/grid/?day=YYYY-MM-DD&limit=200` | One day's guide grid: `grid` is a list of `{channel, airings}` for every channel. It's where the streaming channels' guide comes from: about 3,300 airings a day, thinning out after a week. Airings have `identifier`, `title`, `kind` (`episode`, `movieAiring`, `sportEvent`), `datetime`, `duration`, `description`, `genres`, `qualifierTags`, `images` (`coverLarge`, `background`, ...), `episode` (`season.number`, `episodeNumber`) and `show` (`identifier`, `title`, `category`: `series`, `special`, `feature-film`, `sports-event`, ...). Some airings have no genres, and some clip shows are labelled `feature-film`. |

A 401 or 403 means the cloud sign-in has expired: sign in again.

**Recording streaming channels.** The lineup marks which streaming channels the Tablo may record with `canRecord: true`. Seen on 2026-10-21 in one account's lineup of 101 streaming channels: 68 were `true`, from 38 partners including all of Scripps's (Tablo's owner); every Warner Bros. Discovery (20) and AMC (13) channel was `false`. Recording one is the same request as for an antenna airing, sent to the cloud guide's airing ID: `PATCH /guide/LH-<…>?lh` with `{"scheduled": true}` (captured from Tablo's Android app, 2026-10-21). `schedule.state` on that object then reads `scheduled`, and `GET /views/guide/upcoming?lh` (the app's upcoming list: `[{key: date, contents: [airing IDs]}]`, antenna and streaming together) includes it. The recording uses one of the Tablo's streaming tuner slots, not an antenna tuner. It's an ordinary `/recordings/series/episodes/{id}` object (H.264 + AAC, channel flags `mpeg4`), listed only with `?lh` (see above).

**Keep tokens private.** The Lighthouse token appears in these URLs, so logs and output you share should mask it. TabloView's API inspector shows only its first and last four characters.

## Unknown

Things the Tablo app does that we haven't seen the request for:

- **Channel scan**, and Tablo settings (recording quality, padding, and so on).
- **Manual (time-based) recordings.**
- **Every `skip_reason` value**, and every recording `error` value.

Found one of these? Open an issue or pull request with the method, path and body (never your `Authorization` header or tokens).
