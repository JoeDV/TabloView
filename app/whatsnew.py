"""'What's new' card shown once after TabloView updates (the only way Store users hear about changes).

The last version shown is kept in settings ('last_seen_version'). A fresh install starts as seen,
so new users aren't greeted with release notes; someone who already used an older version (there
was a sync before this run started) sees the notes for the current version.
"""

from typing import Any, Dict, List

from .config import APP_VERSION
from .database import get_sync_meta
from .settings import load_settings, save_settings

# Newest first. Keep in step with packaging/release-notes.txt and the Store listing's "What's new".
NOTES: Dict[str, List[str]] = {
    "1.4.2": [
        "Arrange groups (Live TV → More) has a Bottom button beside Top, and a switch on each group to hide or show it right there.",
        "Fixed: Customize on Home couldn't save any change in 1.4.1.",
        "Fixed: some error messages said [object Object] instead of what went wrong.",
        "Fixed: a long What's new, or any long window like it, ran off the bottom of the screen; the text now scrolls and the buttons stay in view.",
    ],
    "1.4.1": [
        "Guide alerts: save words to watch for, such as a team, a movie or a special (Guide alerts on Home, or Alerts on the Guide page). Shows in the guide with one in their title appear on Home with a Record button, and a notification says when new ones turn up.",
        "Recordings on your Roku, in VLC or Kodi, or on a smart TV: with your antenna channels shared, Roku Media Player and the others now have a Recordings folder beside Live TV, with a folder for each show. Skipping ahead or back starts the recording again at that point.",
        "Recording now: a show's card says so while its newest recording is still being made, on the PC and in the TV view.",
        "Real show artwork: shows that only had a stock picture on your Tablo (remotes and pretzels) now get their real poster from Tablo's online guide.",
        "Exports mark the commercial breaks as chapters, so Plex, Jellyfin, Kodi and VLC can jump past each one, and can save the captions as a .srt file beside the MP4 (both in Settings → Storage & exports).",
        "The timeline is easier to grab and says Commercial break or Signal dropout when you point at one; the player fits narrow windows and phones better, and lighter grey text is easier to read.",
        "Safer: backups, the Claude key and Start with Windows can only be changed on the computer running TabloView, and its fonts are part of TabloView now, so pages no longer contact Google.",
        "Docker: your settings go in tabloview.env, so updating never clashes with them, and an Intel graphics chip converts the video instead of the processor.",
    ],
    "1.4.0": [
        "Watch your antenna channels on a Roku, in VLC or Kodi, or on a smart TV: with Settings → Live TV → Share your antenna channels with other apps turned on, TabloView shows up on your network as a media server. Open Roku Media Player (or your player's network or media server list), pick TabloView, then Live TV and a channel. No address to type.",
        "Several playlists in Live TV → More: add more than one playlist and switch between them in Settings → Live TV or with the picker in More. Each keeps its own favorites, hidden channels and group order.",
        "Arrange groups: in Live TV → More, put your playlist's groups in the order you like.",
        "A new switch in Settings → Playback: Stop where I land when searching. Turn it off and a recording plays on straight away after you skip or click the timeline, instead of waiting for Play.",
        "TabloView can run in Docker on a home server (Linux), set up from one file with your Tablo sign-in, PIN and the computers allowed to change its settings. See DOCKER.md on GitHub.",
        "Settings → Live TV notes that Plex can use its own guide by ZIP code with the TabloView tuner, and suggests keeping this PC's network address fixed so other apps keep finding it.",
        "Fixed: in Chrome, Edge and other Chromium browsers, the sound could turn slow and garbled after jumping around a recording, until you paused for a while.",
    ],
    "1.3.9": [
        "Use your Tablo in Plex, Jellyfin, Emby or Channels DVR: turn on Settings → Live TV → Share your antenna channels with other apps, and TabloView answers like an HDHomeRun tuner, with your Tablo's guide. Settings shows the address to enter in each app. Each channel they watch or record uses one of your Tablo's tuners.",
        "Exports without the commercials: turn on Settings → Storage & exports → Leave out commercial breaks, and MP4 exports skip the breaks TabloView found. Your recording on the Tablo isn't changed, so you can always export it again in full.",
        "Two channels at once: Add a channel now lists every channel, your favorites first, then the list you're watching from, then the rest. On a TV, ◀ ▶ jump a list at a time.",
        "Live TV → More: channel names have about three times the room, and Show the hidden channels sits beside the group picker.",
        "Microsoft Store copies check every half hour for an update that's waiting on Microsoft, and Settings → About & diagnostics shows where your settings really are.",
        "Fixed: captions stopped after jumping ahead, resuming later or going back into a recording, until the page was reloaded.",
    ],
    "1.3.8": [
        "Guide → For you: shows coming up on your antenna channels that you aren't recording yet, picked to suit the series you do record, each with a line on why. New series and new seasons are listed first, under Premiering soon. With a Claude key, Claude picks them; without one, they're matched by genre.",
        "Live TV → More: pick one of your playlist's groups from the list above the channels, or hide a whole group you never watch. On a TV, More opens on the groups.",
        "Big playlists work: a provider's list of hundreds of thousands of entries no longer freezes Live TV. More shows 200 channels at a time, and search looks through the whole list. Only the channels you star go into Favorites and On now.",
        "Movies and series episodes in a playlist are left out, so Live TV lists live channels only. Settings → Live TV says how many were left out.",
        "On a TV, Add a channel is always there in live TV. If the TV doesn't have enough memory for two pictures, pressing it says so.",
        "Fixed: a station's box that stays on screen the whole time, like a weather box with the time and temperature, was taken for the network logo, and no commercial breaks were found.",
        "Fixed: with a Claude key, a scene where the channel's logo stays on (a daydream or flashback, for example) could be taken for a commercial break.",
    ],
    "1.3.7": [
        "Settings has a new look: its sections are listed on the left, and each setting is one row, with what it does on the left and its switch or button on the right. Search settings finds any setting from every section. Help is laid out the same way, with its own search.",
        "Two channels at once on your TV: in live TV, press OK, then Add a channel. ◀ ▶ choose which one you hear, ▲ ▼ change it, and Back closes the other. If the TV can't keep up with two pictures, TabloView closes one by itself.",
        "Moving to a new PC: Settings → About & diagnostics saves everything you've set up (settings, show options, the Watch list, reminders, commercial breaks already found) in one file to restore on the new PC. Sign-ins and the PIN aren't in it, so the file is safe to keep anywhere.",
        "When your Tablo's drive is 90% full, a notice says how much is left and which shows' watched recordings take the most space. Press × to hide it until the drive reaches 95%.",
        "The Skip break message can be put away while you keep watching: × on the PC, Back on a TV.",
        "Microsoft Store copies: Check now says when a new version is out but still waiting for the Store's approval, instead of \"You're on the latest version\".",
        "Fixed: a weather alert banner in the corner of the picture could be taken for the network logo, turning parts of a show into long \"breaks\". Recordings this affected are checked again by themselves.",
        "Fixed: Find again and Find commercials with Claude did nothing on a recording whose breaks were already found. Also fixed: live TV didn't start after a recording was left stopped on a spot.",
    ],
    "1.3.6": [
        "Searching through a recording stops where you land: skip ahead or back, or click the timeline, and the picture waits there until you press Play (OK on a TV).",
        "Exports keep 5.1 surround sound when the broadcast has it. Recordings that are stereo stay stereo.",
        "Split view: each channel has its own CC button, so you can turn the second channel's captions off when they cover the score.",
        "On a TV, OK during a commercial break brings up the controls with Skip break first, so you can pause or rewind in a break too. Press OK again to skip.",
        "A \"break\" over 7 minutes long is more likely part of the show, so it's marked but no longer skipped on its own.",
        "Captions in the TV view have the same cleaner look as on the PC.",
        "Fixed: on some recordings, the Spanish captions were shown on top of the English ones.",
    ],
    "1.3.5": [
        "More channels: add channels from outside your Tablo under Settings → Playback → More channels, and they appear in Live TV under More, on the PC and in the TV view. They don't use a Tablo tuner, and they're watch only: they can't be recorded.",
        "One click sets up Tubi's free channels with a full guide. The list is kept up by a volunteer, so Tubi's channels can come and go from day to day. You can also use iptv-org's larger list (no guide), or a playlist of your own.",
        "Star a More channel to put it under Favorites and in On now, or hide the ones you don't want.",
        "Remind me: since More channels can't be recorded, a show's details offer Remind me. When it starts, TabloView tells you, with a Watch button.",
        "Tailscale: a new switch under Settings → Desktop & network lets your own phones and laptops on Tailscale skip the PIN. It's off unless you turn it on.",
        "Fixed: captions didn't show on PCs with AMD graphics. With captions on, that stream is now converted by the processor, which keeps them; with captions off nothing changes.",
        "Fixed: some streams loaded but never played, and visitors through Tailscale Funnel shared one wrong-PIN lockout.",
    ],
    "1.3.4": [
        "A recording that's still in progress now plays from the beginning (or where you left off), instead of joining at the live end.",
        "Commercial skip uses the show's own TV rating (the TV-14 box in the corner that ABC, NBC and CBS show as the show comes back): a skip never runs over it, and promos left playing just before it are skipped too. On an SVU episode it skipped 26 seconds less of NBC promos left playing and stopped cutting 10 seconds into the show. It applies to recordings scanned from now on.",
        "Away from home: under Settings → Playback you can choose a smaller picture (720p or 480p) for watching over Tailscale on a slow connection. It stays at the full picture unless you change it, and nothing changes at home.",
        "Find again now shows that it ran: the status line says \"Found the commercials again\", and hovering over a recording's commercials tag shows when its breaks were found.",
        "After a new router or internet provider, when Windows calls your home network Public and keeps other devices out, TabloView now suggests switching it to Private first.",
        "Fixed: in split view, the second channel's captions were a different size from the first's.",
    ],
    "1.3.3": [
        "Commercial skip is much better on CBS without a Claude key: TabloView now spots CBS's see-through eye in the corner. On Survivor it skips 96% of the ads (60% before) and on The Price Is Right 99% (90% before), with none of the show skipped.",
        "A stretch of show is no longer taken for a long commercial break: Survivor's Tribal Council used to be skipped as a 10-minute break.",
        "Undo a skip: if an automatic skip cut into the show, press Undo on the message (or U). On a TV, press Up within a few seconds. It goes back to where the skip started, and that part is never skipped again in that recording.",
        "Find again: a button beside Skip commercials on a show's page finds the breaks again in its unwatched recordings with the improved finder (or Find commercials again in a recording's ⋯ menu). Updates don't redo anything by themselves, and a redo now takes seconds for recordings found from now on.",
        "Select a whole season on a show's page: Select… picks a season, the recordings without one (Tablo's \"Other\"), or the watched or unwatched ones, to delete, export or add to the Watch list together. Shift-click ticks every recording in between.",
        "TV view: a show's page has Delete watched, to clear its watched recordings in one go (protected ones are kept).",
        "With a Claude key: if Claude can't be reached, it's asked again later (the recording shows No Claude meanwhile), and Settings now says what it costs: about 5 cents per hour of TV.",
        "Fixed: the commercial break at the very start of a recording could run into the opening of the show.",
    ],
    "1.3.2": [
        "Find commercials with Claude: add your own Anthropic API key under Settings → Playback, and Claude looks at each recording's preview pictures to find the breaks. It's far more accurate on channels without a logo in the corner, like CBS: on a Survivor episode it skipped 99% of the ads and none of the show, where TabloView alone skipped ten minutes of Tribal Council. Each recording costs a few cents on your Anthropic account, and the pictures are sent to Anthropic.",
        "With a key added, recordings that already have their breaks found are done again once, and any recording can be done again with Claude from its ⋯ menu.",
        "TV view: press Down to bring up the player's controls at any time, even during a commercial break (OK skips the break), so remotes without rewind and fast-forward buttons, like the Google TV Streamer's, can always reach them.",
        "TV view: while a recording or channel starts, its picture is shown behind \"Starting…\" instead of a big grey play button, and the title bar now fades by itself once it plays.",
        "TV view reloads itself after TabloView on your PC is updated, so the TV app always has the newest features without restarting it.",
    ],
    "1.3.1": [
        "Commercial skip is more accurate on ABC: skips no longer run on into the show after a break, and bright scenes in the show are no longer mistaken for breaks. Recordings you haven't watched are looked at again once, in the background.",
        "TV view: pressing left or right (or rewind and fast-forward) shows a picture of where you're skipping to, with the time, like on the PC.",
        "ABC and Fox recordings play more smoothly on TVs and slower devices: with Smooth motion off they now play at 30 frames a second like other channels, with half the data.",
        "The signal-dropout check now shows in the status line (the recording, how far along, and what's waiting), and Settings → Playback has a switch to turn it off.",
        "Fixed: when captions showed two or three lines at once, they could pile up in one spot, so the line scrolling away showed through the new one like a shadow.",
    ],
    "1.3.0": [
        "Plex: sign in under Settings → Plex, and Plex picks up each new export right away. Once it's there, it's marked watched in Plex if you watched it (or resumes where you stopped), and if Plex matched it to the wrong show, TabloView fixes the match.",
        "A show's page marks the recordings Plex has already (In Plex) and asks before exporting one again. Turn on Delete once in Plex to have a show's recordings removed from your Tablo once Plex has them.",
        "Exports work better with Plex, Jellyfin and Kodi: the title, show, season and episode, description and air date are written into every MP4, and you can have them sorted into show and season folders, with an optional .nfo file beside each one (Settings → Storage → Exports).",
        "Choosing the export folder uses Windows' own folder picker, so network drives and NAS shares show up, and you can type a path like \\\\NAS\\TV. Exports to a network folder are made on this PC and copied over when finished.",
        "Customize Home: put Home's sections in your own order and hide the ones you don't use. TV view's Home follows it.",
        "A show opened from the Guide or Scheduled has the same controls as in the Library when it has recordings, and Skip commercials can be turned on before anything has recorded.",
        "TV view shows how each recording turned out, like the PC does: failed, partial or short recordings, signal problems, commercial breaks found and protected recordings. The Device page is now called Settings.",
        "Fixed: a recording deleted from the Tablo by another app stayed in the Library until the next sync, and a recording could keep saying Recording after it had finished.",
    ],
    "1.2.9": [
        "TV view is redesigned: a menu down the left side (press Left or Back to open it), Home rows for Continue watching, On now, Recently recorded and Recording soon, a page for each recording with Play, Watch list, Mark watched, Protect and Delete, and a Coming up list of what will record.",
        "TV view's Live TV has a Guide of the next 6 hours: select a later show to record it. While watching live TV, Record (press OK) records what's on.",
        "Export to MP4 automatically: turn on Export to MP4 on a show's page, and each new recording is saved as an MP4 once it finishes recording.",
        "Exports of shows without season and episode numbers are named by the date they aired, and A to Z sorting skips A, An and The.",
        "The Device page lists the devices using TabloView, with recent sign-ins and wrong PINs, and Copy diagnostics gives a summary to paste into the forum, without your sign-in details.",
        "Safer network access: wrong PINs lock a device out for longer each time, your Tablo account and network access can only be changed on this PC, and the TV app asks before using the computer it finds (update it the same way you installed it).",
        "Fixed: several exports started together could save over each other.",
        "Fixed: a damaged settings file could lose your settings and PIN, and deleting every recording on the Tablo left them showing in the Library.",
    ],
    "1.2.8": [
        "New: the TabloView app for Google TV and Fire TV. It puts TV view on your TV's home screen, and the remote moves from tile to tile like any other app, with no pointer to drag around. To install it, get the Downloader app on the TV and enter this PC's address with /app on the end; Help → Watching on your TV has the steps.",
        "Away from home: with Tailscale (free) on this PC and your phone or laptop, you can watch from anywhere. The Device page shows the address to use, and Help explains it.",
        "The Device page now warns when Windows Firewall is keeping your TV and other devices out, and says how to fix it.",
        "Commercial skip catches more: a dark ad at the start or end of a break that looks like the show is now skipped too. Recordings you haven't watched are looked at again once, in the background.",
        "TV view lists a show's episodes oldest first, as on the PC, and opens at the first one you haven't watched.",
        "Help has an About and licenses section.",
    ],
    "1.2.7": [
        "Smoother recordings: the small glitch every 5 or 6 minutes of playback is gone.",
        "Commercials are found much sooner: about 3 minutes per half hour of recording instead of 8, while nothing else is playing.",
        "Network status on the Device page (Desktop & network): how your Tablo and this PC are connected, with a Test connection button that checks the speed between them.",
        "Live TV favourites: the favourite channels you set in Tablo's own apps now show under Favorites.",
        "TV view: commercial breaks are marked and skipped as on the PC, a CC button turns captions on, and the next episode of a show plays when one ends. A TV view button at the top right of the PC page switches to it.",
        "Mac and Linux: Network access lets your other devices use TabloView, as on Windows.",
        "Fixed: if your Tablo got a new address on your network, TabloView now finds it again instead of saying the Tablo isn't responding. Help has steps for when it still doesn't respond.",
    ],
    "1.2.6": [
        "Commercial skip finds whole breaks now, not just part of them. It looks for the channel's logo in the corner of the picture (most networks take it off during ads), the moment of black and silence at each break's edges, and, on channels without a logo, how different the picture looks from the show. In our tests it skips 80-100% of the ads during a show, and it never skips past the end of a show.",
        "Recordings whose breaks were found the old way are looked at again once, in the background, unless you've already watched them.",
        "Help: a guide to everything TabloView does, at the bottom of the sidebar.",
        "TV view: Recordings is now called Library, as on the PC, and opens with wide pictures; switch to posters at the top.",
        "Fixed: Open in VLC didn't play recordings.",
    ],
    "1.2.5": [
        "TV view: big screens for a TV's browser (TV Bro on Google TV, Silk on Fire TV), used with the remote. Continue watching, Recordings, Live TV and your Watch list, with large buttons for pause, skip and close. Choose it under Device → Appearance → View on this device, or open your TabloView address with /tv on the end. New, so tell us how it works on your TV.",
        "Picture shape for each channel: some stations send a squeezed, stretched or boxed-in picture. Choose Auto, 4:3, 16:9 or Zoom from the player (or press A), and TabloView remembers it for that channel, for live TV and its recordings.",
        "A stream nobody is watching any more (a TV browser switched off, a laptop gone to sleep) is closed after 10 minutes, so it no longer holds a tuner, slows exports or pauses commercial finding.",
        "Save exports to: the folder window now opens in front, and if it can't open you can type the folder instead.",
        "Security: other devices no longer receive the network PIN's details, and HTTPS uses an updated list of trusted certificates.",
        "Fixed: skipping ahead several times quickly could leave copies of the stream running and slow everything down, and L skips ahead 30 seconds again (two-channel layouts moved to V).",
    ],
    "1.2.4": [
        "Refresh guide now asks your Tablo to download the latest guide first (like its own app's Update guide button), shows how far along it is, then loads it.",
        "Faster exports: Original exports run several times faster than real time while nothing else is playing from your Tablo, and slow down by themselves when something starts, so watching isn't affected.",
        "Record streaming shows from the live player, on the streaming channels your Tablo is allowed to record.",
        "Playback and live TV recover by themselves when a stream gets stuck, instead of stopping with \"Live TV stopped responding\".",
        "Faster pages, especially while TabloView is syncing or when used from another device at home.",
        "Macs use Apple's graphics encoder for exports and Smaller quality, instead of the processor.",
        "Mac and Linux: Stop TabloView on the Device page (Desktop & network), no need to close Terminal. Windows: the first time you close the last TabloView page, the tray says it's still running and how to quit it.",
        "Fixed: Continue watching listed recordings you'd only started for a moment.",
    ],
    "1.2.3": [
        "Streaming channels in the Guide: a new Streaming channels tab with a week of shows, sorted into categories (News, Sports, Movies and more), with search.",
        "Record streaming shows: on the many streaming channels your Tablo is allowed to record, choose Record in the Guide or in Live TV. They show in Recording soon, Scheduled, Live TV and your Library like any other recording.",
        "Watch list: add recordings from any show and play them one after another. Choose Watch and delete to clear each one out once you've watched it to the end (protected recordings are always kept).",
        "See what your tuners are doing: click Tuners at the top of any page to see what each one is recording or playing, and which are free.",
        "Channel logos and numbers in Recording soon and Scheduled.",
        "Scheduled shows New episodes your Tablo won't record because it decided they aren't new, with a Record button.",
        "A tidier Device page, in tabs.",
        "Fixes: the Guide's Movies filter now shows movies, Live TV's streaming channels no longer go blank after 9 PM, and Check now for updates works in the Microsoft Store version.",
    ],
    "1.2.2": [
        "Signal dropouts in recordings: when your Tablo says a recording didn't come in cleanly, TabloView finds the parts where a weak signal broke up the picture and marks them in red on the timeline. Skip them with the Skip dropout button (or S), or have TabloView skip them for you (Device → Playback). Episodes with dropouts are tagged on the show's page.",
        "Record from the live player: a Record button records the show you're watching.",
        "Choose the page TabloView opens on (Device → Appearance).",
        "Exports can be cancelled and removed, and a recording the Tablo stops sending no longer leaves an export stuck. If it stops near the end, you keep what arrived.",
        "Back-to-back recordings on the same channel no longer trigger a \"Not enough tuners\" warning.",
        "Sign-in works even with a space before or after your email, and the Store update check says what to do instead of showing a Windows error.",
    ],
    "1.2.1": [
        "Antenna helper (Antenna in the sidebar): aim your antenna with a big live picture-quality readout, a tone that rises as reception improves, a check of all your channels, and saved positions to compare. Open TabloView on your phone and take it to the antenna.",
        "Channel logos in the stations' own colors. Prefer them white? Device → Appearance.",
        "Scheduled now shows the episodes your Tablo won't record because more shows overlap than it has tuners, marked Won't record, so nothing quietly goes missing on a busy night.",
        "The signal meter no longer makes heavy breakup look worse than it is.",
        "A clear message when the Tablo can't pick up a channel, instead of a technical error.",
        "If the TV guide doesn't finish loading, TabloView says so and tries again within minutes; recordings no longer drop out of the Library when a sync is cut short.",
        "Live TV guide pages stay on the hour and half hour, and the Library count in the sidebar stays put.",
    ],
    "1.2.0": [
        "Live signal meter: on antenna channels, a badge beside the channel name shows how much of the picture is reaching you, second by second. Click it for the last 5 minutes. Handy while aiming an antenna.",
        "Sports in the Guide are grouped by sport and league (Football: NFL, College; Soccer: Premier League, Liga MX…), and each game is listed by matchup.",
        "Choose where MP4 exports are saved: Device → Playback → Save exports to.",
        "Live TV switches from Smooth motion to standard by itself if your PC can't keep up, instead of falling behind.",
        "Changing channels is more reliable on 2-tuner Tablos, and when every tuner is busy TabloView says why, with Try again and Watch a recording.",
        "Fixed: the Guide's Sports filter showed nothing, and league pages had no games.",
    ],
    "1.1.7": [
        "Watch two channels at once: add a live channel next to live TV or a recording (the button with two rectangles, or press 2). Side by side, big and small, or full screen; Tab switches the sound, and the silent one shows captions and flashes when something big happens.",
        "Back for a new season: shows you've recorded before that are returning, on the Home page and as a notification.",
        "Add your upcoming recordings to Google Calendar, Outlook or Apple Calendar (Scheduled → Upcoming recordings).",
        "Check for updates from the tray icon; the Microsoft Store version now tells you when an update is waiting.",
        "Signal health (Device page): which channels' recordings fail, why, and when, with tips, and a notification when a channel keeps failing.",
        "Closing live TV now frees the tuner on your Tablo right away instead of leaving it reserved.",
    ],
    "1.1.6": [
        "Much faster loading from your Tablo: a new computer's first load takes under a minute instead of 5–10, and \"Tablo isn't responding\" during loading is gone.",
        "A banner shows progress while the TV guide loads for the first time.",
        "Preview frames when you hover over a recording's timeline.",
        "Sleep timer in the player: stop after 15–90 minutes or at the end of the show.",
        "On now: what's airing on your channels, right on the Home page.",
        "Smaller MP4 exports (about a third smaller), and export several episodes at once.",
        "Closed captions in the player: the CC button, or press T.",
        "Skip commercials for the shows you choose: TabloView finds the breaks in the background, marks them on the timeline and gives you a Skip button (or skips them for you).",
        "Recordings that fail or come out short are recorded again from a rerun when there is one.",
        "Partly watched episodes can be marked unwatched again.",
        "Using TabloView from phones or other computers? They now sign in with a PIN (this PC never asks). Set it on the Device page under Network access.",
        "Steadier playback on PCs with Intel graphics: the graphics chip's video encoder no longer drops out every so often.",
        "If the video converter does stop, playback picks up again instead of ending as if the show were over.",
    ],
    "1.1.5": [
        "Sharper playback: your PC's graphics chip converts the video when it can. For sports, try Smooth motion (60 fps) in Device → Playback.",
        "Streaming channels play in their original quality and start faster.",
        "Clearer dialogue in shows with surround sound.",
        "Player controls: skip back 10 s / ahead 30 s, pause, speed, picture-in-picture and full screen, with keyboard shortcuts (press ? in the player).",
        "Pause and rewind live TV, up to 30 minutes.",
        "Change channels without leaving the player: press C for a list of what's on, or Page Up / Page Down.",
        "Protect recordings from deletion (episode menu), and on a show's page choose how many recordings your Tablo keeps, or have watched ones deleted automatically after a few days.",
        "Playback that stalls picks up again on its own.",
        "Recording conflicts can be fixed in a click: TabloView finds another airing of the same episode to record instead.",
        "Far fewer \"Tablo isn't responding\" interruptions: refreshing the guide no longer floods the Tablo with requests. When it does happen, TabloView says so and reconnects on its own.",
    ],
    "1.1.4": [
        "Episode thumbnails taken from the recordings themselves.",
        "Auto-play the next episode when one ends.",
        "Device → Space by show: see which shows use the most space and delete their watched episodes in one click.",
        "Start with Windows (in the tray), and Windows notifications for failed recordings and recording conflicts.",
        "Protected recordings show a lock, and Delete watched skips them.",
        "Clearer tags for recordings that came out short, failed, or had signal problems.",
        "A Favorites filter in Live TV (favorites set in the Tablo app).",
        "Playback starts where the show does, skipping the few seconds the Tablo records early.",
    ],
    "1.1.3": [
        "Available in the Microsoft Store.",
        "No more console windows popping up during playback.",
    ],
    "1.1.2": [
        "Scheduled → Upcoming: every recording coming up, with warnings when more are set to record at once than you have tuners.",
        "Live TV warns before tuning would leave too few tuners for a recording about to start, and shows tuners the Tablo is still releasing.",
        "A timeline in the player to jump around a recording.",
    ],
    "1.1.1": [
        "TabloView tells you when a new version is available.",
        "Live TV: talk shows no longer count as News.",
    ],
    "1.1.0": [
        "Watched status and resume points, shared with the Tablo's own apps.",
        "Live TV works in any TV market.",
        "A banner when your Tablo sign-in has expired, with a button to sign in again.",
        "Recordings sync automatically every 15 minutes (adjustable), and the guide every 6 hours.",
        "Scheduled lists every series set to record, including ones between seasons.",
    ],
    "1.0.0": [
        "First release: recordings, the program guide, live TV, series scheduling and MP4 export for the Tablo 4th Gen, in a Windows app with its own installer.",
    ],
}


def init() -> None:
    """At startup: decide whether this is an upgrade (show notes) or a fresh install (don't)."""
    if load_settings().get("last_seen_version") is None and not get_sync_meta("last_sync"):
        save_settings({"last_seen_version": APP_VERSION})


def pending() -> Dict[str, Any]:
    seen = load_settings().get("last_seen_version")
    notes = NOTES.get(APP_VERSION, [])
    return {"show": seen != APP_VERSION and bool(notes), "version": APP_VERSION, "notes": notes}


def changelog() -> List[Dict[str, Any]]:
    """Every version's notes, newest first, up to the one running (for Device → Version history)."""
    def key(v: str):
        return tuple(int(x) for x in v.split("."))
    return [{"version": v, "notes": n} for v, n in NOTES.items() if key(v) <= key(APP_VERSION)]


def mark_seen() -> None:
    save_settings({"last_seen_version": APP_VERSION})
