# Microsoft Store listing: TabloView for TabloTV

Text to paste into Partner Center. Keep the first line of the description: Store policy 10.2.4 requires a
product's dependencies to be disclosed at the start.

## Product name
TabloView for TabloTV

## Description
Requires a Tablo 4th Gen DVR on your home network and a Tablo account. TabloView is an unofficial app and is not affiliated with or endorsed by Tablo.

TabloView is a fast desktop interface for your Tablo DVR. Browse and play your recordings, search everything airing on your channels, schedule series, and watch live TV, all in your web browser on your PC.

• Home: what's new, what's recording soon, season premieres and new primetime episodes
• Library: play recordings in your browser with resume and a full timeline, mark watched, delete one, several or all watched episodes, export to MP4
• Guide: search the next two weeks of your lineup and record a series (new or all episodes) or single airings
• Live TV: a channel grid for antenna and streaming channels, with recording badges and a warning before live TV takes a tuner a recording needs
• Scheduled: every series your Tablo records, upcoming recordings with Skip, and conflict warnings
• Syncs automatically, and watched status and resume points stay in sync with your Tablo's other apps

Sign in with your own Tablo account. Your password goes only to Tablo's sign-in service and is never saved. TabloView runs only on your PC unless you turn on network access for other devices at home.

## What's new in this version
1.2.0:
• Live signal meter: see how much of the picture is reaching you from your antenna, second by second
• Sports in the Guide grouped by sport and league, with games listed by matchup
• Choose where MP4 exports are saved
• Live TV steps down from Smooth motion by itself if your PC can't keep up
• More reliable channel changes on 2-tuner Tablos, and a clear message when every tuner is busy

1.1.7:
• Watch two channels at once: a live channel next to live TV or a recording, side by side or big and small
• Signal health: which channels' recordings fail, why and when, with antenna tips
• Back for a new season: shows you've recorded before that are returning
• Add your upcoming recordings to Google Calendar, Outlook or Apple Calendar
• Check for updates from the tray icon; the Store version tells you when an update is waiting
• Closing live TV frees the Tablo's tuner right away

1.1.6:
• Skip commercials for the shows you choose: breaks are found in the background and marked on the timeline
• Closed captions in the player
• Preview frames when you hover over a recording's timeline, and a sleep timer
• On now: what's airing on your channels, on the Home page
• Smaller MP4 exports, and export several episodes at once
• Recordings that fail are recorded again from a rerun when there is one
• Much faster loading from your Tablo, and steadier playback on Intel graphics
• Other devices on your network sign in with a PIN

1.1.5:
• Sharper playback: your PC's graphics chip converts the video when it can, with optional 60 fps Smooth motion for sports
• Player controls: skip back/ahead, speed, picture-in-picture, full screen, keyboard shortcuts
• Pause and rewind live TV (up to 30 minutes), and change channels from the player
• Protect recordings, choose how many recordings of a show to keep, or delete watched ones automatically
• Fix recording conflicts in a click by recording another airing instead
• Playback that stalls recovers on its own
• Far fewer "Tablo isn't responding" interruptions
• Version history in Device → About

1.1.4:
• Episode thumbnails from the recordings themselves
• Auto-play the next episode when a show ends (can be turned off)
• Space by show: see what's using your Tablo's storage and delete watched episodes in one click
• Start with Windows, quietly in the tray
• Notifications when a recording fails or stops early, or when recordings conflict
• Protected recordings are marked and kept by "Delete watched"
• Clearer tags for short, partial and failed recordings
• Live TV Favorites filter (uses the favorites set in Tablo's apps)
• Playback from the start skips the few seconds recorded before the show

1.1.3: First Microsoft Store release.

## Product features (one per line)
Play Tablo recordings in your browser with resume
Search the guide and schedule series or single episodes
Live TV channel grid with tuner and recording warnings
Upcoming recordings with conflict warnings
Bulk delete and mark watched
Export recordings to MP4

## Keywords
Tablo, DVR, OTA, antenna, TV, recordings, live TV, guide

## Category
Entertainment (subcategory: none)

## Privacy policy URL
https://gist.github.com/JoeDV/f9c8e1d0151ed3c5339b9a15d6bc0b1d
(public gist holding PRIVACY.md; edit that gist when the policy changes so the link stays the same)

## Copyright and trademark info
© 2026 Joe Del Vecchio. Tablo is a trademark of its respective owner; TabloView is not affiliated with Tablo.

## Age rating questionnaire
No violence, sexual content, profanity, gambling, purchases or user-generated sharing. TabloView shows TV listings and recordings from the user's own DVR; it does not provide or curate content. Answer that the app has no user interaction/sharing features and no purchases.

## Screenshots (at least 1, ideally 4; 1920x1080 works)
1. Home
2. A show page with episodes
3. Live TV grid
4. Scheduled → Upcoming recordings

## Submission options → Notes for certification
TabloView is a companion app for the Tablo 4th Gen over-the-air DVR and needs a Tablo device on the same home network plus the owner's Tablo account, so it can't be fully tested without that hardware. Without a Tablo, the app starts, puts an icon in the system tray, opens its sign-in page in the default browser (http://127.0.0.1:7070), and shows a clear message if sign-in or device discovery fails. Bundled FFmpeg converts recordings for in-browser playback and MP4 export. No data is sent to the developer. Privacy policy: https://gist.github.com/JoeDV/f9c8e1d0151ed3c5339b9a15d6bc0b1d

## Restricted capability justification (runFullTrust; the box holds about 500 characters)
TabloView is a classic Win32 desktop app (Python/PyInstaller) packaged as MSIX, so it needs full trust. It runs a local web server on 127.0.0.1 that the user opens in their browser, talks to the user's Tablo DVR on the home network, launches the bundled ffmpeg.exe to play and export recordings, and shows a system tray icon. No drivers, services or system changes; no self-updating; no data sent to the developer. Letting other devices on the home network open it is optional and off by default.
