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
