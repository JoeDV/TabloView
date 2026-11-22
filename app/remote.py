"""Phone as a remote: a phone on the home network sends buttons, a channel or a show to an open
TV view (the TV app, or /tv in a browser), through TabloView (static/remote.html).

Each TV view asks for its commands with a request that waits until there's one or WAIT_SECONDS
pass (long polling). A connection held open the whole time (server-sent events) kept TabloView
from closing or restarting: uvicorn waits for every response to finish. This way a screen is told
at once, and closing waits a few seconds at most.

Kept in memory only: screens come and go with their pages, and a command nobody collects is
dropped with its screen."""

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

WAIT_SECONDS = 8
GONE_SECONDS = 25  # a screen that hasn't asked for this long has closed
MAX_WAITING = 20  # commands kept for a screen between its requests

# What a phone may send: remote buttons, and the few things the TV view does from a value
KEYS = {"up", "down", "left", "right", "ok", "back", "home", "playpause", "rewind", "forward", "chup", "chdown"}
COMMANDS = {"key", "skipbreak", "tune", "open", "play"}


class Screen:
    def __init__(self, screen_id: str, name: str, clock=time.monotonic):
        self.id, self.name, self.clock = screen_id, name, clock
        self.seen = clock()
        self.state: Dict[str, Any] = {}
        self.commands: List[Dict[str, Any]] = []
        self.ready = asyncio.Event()

    def take(self) -> List[Dict[str, Any]]:
        out, self.commands = self.commands, []
        self.ready.clear()
        return out


screens: Dict[str, Screen] = {}
# Set from the launcher's thread when TabloView closes or restarts (an asyncio.Event can't be set
# from another thread): waiting screens are answered within a second
_closing = threading.Event()


def close_all() -> None:
    _closing.set()


def reopen() -> None:
    """The server started (again, after a restart in the same process: its screens' waits belonged
    to the old server's event loop, and they ask again within seconds anyway)."""
    _closing.clear()
    screens.clear()


def _forget_gone(now: float) -> None:
    for sid in [sid for sid, s in screens.items() if now - s.seen > GONE_SECONDS]:
        del screens[sid]


def screen(screen_id: str, name: str, clock=time.monotonic) -> Screen:
    """This screen, now seen (added if new)."""
    s = screens.get(screen_id)
    if s is None:
        s = screens[screen_id] = Screen(screen_id, name, clock)
    s.name, s.seen = name or s.name, clock()
    return s


async def wait_for_commands(screen_id: str, name: str, wait: float = WAIT_SECONDS) -> List[Dict[str, Any]]:
    s = screen(screen_id, name)
    end = s.clock() + wait
    while not s.commands and not _closing.is_set() and s.clock() < end:
        try:
            await asyncio.wait_for(s.ready.wait(), min(1.0, max(0.0, end - s.clock())))
        except asyncio.TimeoutError:
            pass
    s.seen = s.clock()  # (still here at the end of the wait too)
    return s.take()


def set_state(screen_id: str, name: str, state: Dict[str, Any]) -> None:
    screen(screen_id, name).state = state


def listed(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """The screens open now, the most recently used first."""
    now = time.monotonic() if now is None else now
    _forget_gone(now)
    return [{"id": s.id, "name": s.name, "state": s.state}
            for s in sorted(screens.values(), key=lambda s: -float(s.state.get("at") or 0))]


class RemoteError(Exception):
    pass


def send(screen_id: str, command: str, value: Optional[str] = None) -> None:
    s = screens.get(screen_id)
    if s is None or time.monotonic() - s.seen > GONE_SECONDS:
        raise RemoteError("That screen isn't open any more")
    if command not in COMMANDS:
        raise RemoteError(f"Unknown command: {command}")
    if command == "key" and value not in KEYS:
        raise RemoteError(f"Unknown button: {value}")
    if command == "open" and not (value or "").startswith("#/"):
        raise RemoteError("Only TabloView's own pages can be opened")
    if command in ("tune", "play", "open") and not value:
        raise RemoteError("Nothing to tune or play")
    s.commands = (s.commands + [{"command": command, "value": value}])[-MAX_WAITING:]
    s.ready.set()
