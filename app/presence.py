"""Whether a TabloView page is open in a browser: open pages ask /api/library/status every few
seconds, so a long silence means the last one was closed. The tray uses it to say, once, that
TabloView keeps running after the browser closes (people expected closing it to quit)."""

import time
from typing import Optional

# Browsers slow the timers of tabs in the background to about once a minute, so wait well past that
PAGE_GONE_SECONDS = 180

_last_seen = 0.0


def page_seen(now: Optional[float] = None) -> None:
    global _last_seen
    _last_seen = now or time.time()


def pages_closed(now: Optional[float] = None) -> bool:
    """A page was open since TabloView started, and none has been heard from for a while."""
    return bool(_last_seen) and (now or time.time()) - _last_seen > PAGE_GONE_SECONDS
