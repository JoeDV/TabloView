# Contributing to TabloView

Thanks for your interest! TabloView is a one-person hobby project, so here's how to help in a way that's easy to take in.

## Reporting a bug or suggesting a feature

Open an [issue](https://github.com/JoeDV/TabloView/issues/new/choose) and pick **Bug report** or **Feature idea**. Please include your TabloView version and Tablo model, since a lot depends on the number of tuners. Never post your Tablo account email, password or PIN.

## Code changes

Pull requests are welcome, but please open an issue first for anything bigger than a small fix, so we can agree on it before you spend time on it.

- Run it from source with `start.ps1` (Windows), or see [MAC.md](MAC.md) and [LINUX.md](LINUX.md).
- Run the unit tests with `python -m unittest discover -s tests/unit -t .` before sending a change.
- Tests must never change anything on a real Tablo (recordings, schedules, settings). Fake those calls.
- Go easy on the Tablo: it refuses connections for about a minute after a burst of requests, so fetch in batches (`fetch_objects` in `app/sync_service.py`) rather than one request per item.
- What we know about the Tablo's (unpublished) API is in [TABLO-API.md](TABLO-API.md). Found something new? Add it there.
- Keep wording in the app plain and short. TabloView is used by people who aren't technical.

By sending a pull request you agree that your change is shared under this project's [license](LICENSE).
