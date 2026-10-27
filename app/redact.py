"""Sign-in details kept out of what TabloView prints and shares.

Its log is often pasted into forum posts, and Tablo's cloud addresses carry the account's Lighthouse
token in the path (/api/v2/account/<token>/...), so an error message that repeats the address put it in
the log. Everything printed (and uvicorn's own messages) goes through scrub() once install() runs:
the account's tokens and email, any account path and Bearer value, are replaced.
"""

import logging
import re
import sys
from pathlib import Path
from typing import List

HIDDEN = "<hidden>"
_ACCOUNT_PATH = re.compile(r"(/api/v2/account/)[^/\s'\"?]+")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+")


def _secrets() -> List[str]:
    try:
        from .tablo_client import tablo_manager
    except Exception:
        return []
    values = [tablo_manager.email]
    for dev in [tablo_manager.device, *tablo_manager.devices]:
        if dev:
            values += [dev.lighthouse_token, dev.account_token]
    return [v for v in values if isinstance(v, str) and len(v) >= 6]


def scrub(text: str) -> str:
    if not text:
        return text
    for secret in _secrets():
        text = text.replace(secret, HIDDEN)
    text = _ACCOUNT_PATH.sub(r"\1" + HIDDEN, text)
    return _BEARER.sub(r"\1" + HIDDEN, text)


def scrub_paths(text: str) -> str:
    """Also the Windows user name in folder paths (C:\\Users\\<name>\\...), for text meant to be shared."""
    home = str(Path.home())
    return text.replace(home, "%USERPROFILE%").replace(home.replace("\\", "/"), "%USERPROFILE%")


class _Scrubbed:
    """A text stream that scrubs what's written to it."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        try:
            text = scrub(text)
        except Exception:  # printing must never fail because of this
            pass
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install() -> None:
    """Scrub everything printed from now on: stdout, stderr, and the log handlers uvicorn set up."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is not None and not isinstance(stream, _Scrubbed):
            setattr(sys, name, _Scrubbed(stream))
    for logger in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(logger).handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler.stream, _Scrubbed):
                handler.setStream(_Scrubbed(handler.stream))
