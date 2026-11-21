# TabloView privacy policy

_Last updated: November 21, 2026_

TabloView ("TabloView for TabloTV" in the Microsoft Store) is an unofficial app for Tablo DVRs, made by Joe Del Vecchio. It is not affiliated with or endorsed by Tablo or its owners.

**In short: TabloView doesn't collect anything about you. Nothing is sent to the developer.** A few features you choose to turn on use other services; each is described below, and none is on unless you set it up.

## What TabloView handles, and where it goes

- **Your Tablo account email and password.** When you sign in, they are sent only to Tablo's own sign-in service, the same one Tablo's apps use, to get access to your Tablo. Your password is never saved. Your email and the device access Tablo returns are stored on your computer so you stay signed in.
- **Your recordings, guide and settings.** TabloView reads these from your Tablo on your home network and from Tablo's guide service, and keeps a cache on your computer so pages load quickly. Changes you make (recording rules, deletions, watched status and resume points) are sent to your Tablo. Show artwork and channel logos are loaded from Tablo's own image servers, as in Tablo's apps.
- **Video.** Recordings and live TV are streamed from your Tablo and converted on your computer for playback in your browser. Finding commercial breaks and signal dropouts also happens on your computer, unless you turn on Claude (below). MP4 exports are saved to the folder you choose, and a calendar file of your upcoming recordings is only created when you download it.
- **Update checks.** The downloaded version reads a small public file on GitHub listing the latest version number. The Microsoft Store version asks the Microsoft Store, through Windows, whether an update is waiting. Nothing about you is sent beyond what any web request includes, such as your IP address.

TabloView has no analytics, ads, tracking or crash reporting, and the developer runs no servers that receive your data. Its pages, fonts and player are all served by TabloView itself.

## Features that use other services (only if you turn them on)

- **Finding commercials with Claude.** If you add your own Anthropic API key, the Tablo's preview pictures of each recording (one about every 10 seconds, small and labelled with their times) are sent to Anthropic, whose Claude model says where the commercial breaks are. The same key lets Claude pick shows for Guide → For you: for that, only the titles and genres of the series you record and of the shows coming up are sent, nothing about what you watch. Anthropic's own privacy policy and terms apply, and the cost is billed to your Anthropic account. Your key is stored on your computer, and you can remove it at any time.
- **Plex.** If you sign in to Plex, TabloView gets a sign-in from plex.tv (you approve it on Plex's own page), finds your Plex servers through plex.tv, and then talks to your Plex server directly: it tells Plex about new exports, copies watched status and resume points to it, and corrects a show it matched wrongly. The Plex sign-in is stored on your computer.
- **More channels (playlists).** If you add a playlist or guide address, TabloView downloads it from that address, and the channels play from the addresses the playlist lists. Those sites see your IP address, as with any web request. The quick setups use a volunteer's list of Tubi's free channels and iptv-org's public list, both on GitHub.
- **Sharing your Tablo with other apps.** If you turn this on, Plex, Jellyfin, Emby, Channels DVR, Roku Media Player, VLC, Kodi and smart TVs on your home network can find TabloView and play your antenna channels and their guide. Nothing goes outside your home network for this.
- **Watching away from home.** This works only through Tailscale, which you install and sign in to yourself; Tailscale's privacy policy applies to it.

## Where your data is stored

Everything TabloView keeps stays on your computer, in its app data folder (shown under **Settings → About & diagnostics**). Signing out removes your Tablo access. Uninstalling a Microsoft Store copy removes its app data. For the downloaded version, delete `%LOCALAPPDATA%\TabloView` after uninstalling. A backup you save contains your settings and lists but no sign-ins, keys or PIN.

By default TabloView can only be opened from the computer it runs on. If you turn on **Network access**, other devices on your home network can open it after entering the PIN you choose. The PIN is stored only as a scrambled (hashed) value. **Copy diagnostics** puts a summary on your clipboard for you to share if you want help; it leaves out your sign-in details, email and Windows user name.

## Third parties

Your Tablo account and device are covered by Tablo's own privacy policy. Apart from the services you choose to use above, TabloView shares nothing with anyone else.

## Children

TabloView is not directed at children and collects no personal information from anyone.

## Changes and contact

If this policy changes, the date above is updated. For questions, find the TabloView thread on the [Tablo Community Forum](https://community.tablotv.com/), or message JoeDV there.
