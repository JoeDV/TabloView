"""TabloView desktop launcher.

Runs the local web server, opens TabloView in the default browser, and keeps a system-tray icon
(Open / Downloads folder / Quit). This is the entry point for the packaged Windows app; developers
can still run `python -m uvicorn app.main:app` directly.
"""

import asyncio
import os
import sys
import json
import time
import socket
import threading
import webbrowser
import urllib.request


LOG_LIMIT = 2 * 1024 * 1024  # then tabloview.log becomes tabloview.old.log and starts again


class _LogFile:
    """tabloview.log, started again once it passes LOG_LIMIT: at start-up and while running (a PC left on
    for weeks used to grow it without end). Written from several threads."""

    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        self._rotate_if_big()
        self.f = open(path, "a", encoding="utf-8", buffering=1)

    def _rotate_if_big(self):
        try:
            if self.path.exists() and self.path.stat().st_size > LOG_LIMIT:
                self.path.replace(self.path.with_name("tabloview.old.log"))
        except OSError:
            pass

    def write(self, text):
        with self.lock:
            n = self.f.write(text)
            if text.endswith("\n") and self.f.tell() > LOG_LIMIT:
                self.f.close()
                self._rotate_if_big()
                self.f = open(self.path, "a", encoding="utf-8", buffering=1)
            return n

    def flush(self):
        with self.lock:
            self.f.flush()

    def __getattr__(self, name):
        return getattr(self.f, name)


def _setup_logging():
    """A windowed (no-console) build has no stdout/stderr; send all output to a log file."""
    from app.config import LOG_DIR
    sys.stdout = sys.stderr = _LogFile(LOG_DIR / "tabloview.log")
    print(f"\n===== TabloView starting {time.strftime('%Y-%m-%d %H:%M:%S')} =====")


if sys.stdout is None or getattr(sys, "frozen", False):
    _setup_logging()

from app.config import APP_NAME, APP_VERSION, DOWNLOADS_DIR, IS_STORE, LOG_DIR, STORE_LINK  # noqa: E402
from app.settings import load_settings, save_settings, exports_dir  # noqa: E402
from app import notifications, presence, startup, updates  # noqa: E402


def running_tabloview(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/system/info", timeout=1.5) as r:
            return json.load(r).get("app") == APP_NAME
    except Exception:
        return False


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


class ServerRunner:
    """Owns the uvicorn server thread and restarts it when settings change (e.g. network access)."""

    def __init__(self):
        self.server = None
        self.thread = None
        self.port = None
        self.host = None
        self.restart_requested = threading.Event()
        self.stopping = False

    def choose_port(self, preferred: int) -> int:
        for port in range(preferred, preferred + 20):
            if port_free(self.host, port) and port_free("127.0.0.1", port):
                return port
        raise RuntimeError("No free port found for TabloView")

    def start(self):
        import uvicorn
        from app.main import app

        settings = load_settings()
        self.host = "0.0.0.0" if settings.get("allow_lan") else "127.0.0.1"
        # Keep the same port across restarts so open browser tabs reconnect
        self.port = self.port if self.port and port_free(self.host, self.port) else self.choose_port(int(settings.get("port", 7070)))

        app.state.runtime = {"host": self.host, "port": self.port}
        app.state.request_restart = self.request_restart

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info", access_log=False)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="tabloview-server", daemon=True)
        self.thread.start()
        print(f"[Launcher] Serving on {self.host}:{self.port}")

    def wait_ready(self, timeout: float = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if running_tabloview(self.port):
                return True
            if self.thread and not self.thread.is_alive():
                return False
            time.sleep(0.25)
        return False

    def request_restart(self):
        """Called from inside the server (settings change); the monitor thread does the restart."""
        self.restart_requested.set()
        if self.server:
            self.server.should_exit = True

    def monitor(self):
        while not self.stopping:
            if self.restart_requested.wait(timeout=1.0) and not self.stopping:
                self.thread.join(timeout=15)
                self.restart_requested.clear()
                print("[Launcher] Restarting server to apply settings...")
                self.start()
                self.wait_ready()

    def stop(self):
        self.stopping = True
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=10)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


def open_folder(path):
    try:
        os.startfile(str(path))  # Windows only
    except Exception as e:
        print(f"[Launcher] Could not open {path}: {e}")


def main():
    settings = load_settings()
    preferred = int(settings.get("port", 7070))
    # Started by Windows at sign-in: stay in the tray instead of opening the browser
    background = startup.launched_at_startup()

    # Already running? Just bring it up in the browser.
    if running_tabloview(preferred):
        if not background:
            webbrowser.open(f"http://127.0.0.1:{preferred}/")
        return

    runner = ServerRunner()
    runner.start()
    if not runner.wait_ready():
        print("[Launcher] Server failed to start; see log above.")
        _fatal(f"TabloView couldn't start. Details are in:\n{LOG_DIR / 'tabloview.log'}")
        return
    threading.Thread(target=runner.monitor, name="tabloview-monitor", daemon=True).start()
    if background:
        print("[Launcher] Started at sign-in; staying in the tray")
    else:
        webbrowser.open(runner.url)

    try:
        import pystray
        from app.icon import draw_icon
    except ImportError:
        # Source checkout without tray dependencies: run until Ctrl+C
        print(f"{APP_NAME} running at {runner.url} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            runner.stop()
        return

    def on_quit(icon, _item):
        icon.visible = False
        runner.stop()
        icon.stop()

    def on_check_updates(icon, _item):
        """Store copy: open TabloView's page in the Store (an update shows there as an Update button).
        Installer copy: check now, and open the download if there's a newer version."""
        if IS_STORE:
            os.startfile(STORE_LINK)
            return

        def check():
            u = asyncio.run(updates.check_for_update(force=True))
            if u.get("update_available") and u.get("download_url"):
                icon.notify(f"Version {u['latest']} is available. Opening the download.", APP_NAME)
                webbrowser.open(u["download_url"])
            elif u.get("error"):
                icon.notify("Couldn't check for updates right now. Try again later.", APP_NAME)
            else:
                icon.notify(f"You have the latest version ({APP_VERSION}).", APP_NAME)
        threading.Thread(target=check, name="update-check", daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Open TabloView", lambda: webbrowser.open(runner.url), default=True),
        pystray.MenuItem("Open exports folder", lambda: open_folder(exports_dir())),
        pystray.MenuItem("Check for updates", on_check_updates),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"{APP_NAME} {APP_VERSION}", None, enabled=False),
        pystray.MenuItem("Quit TabloView", on_quit),
    )
    icon = pystray.Icon(APP_NAME, draw_icon(64), f"{APP_NAME} is running", menu)
    # Recording problems and conflicts are announced from the tray icon
    notifications.set_notifier(lambda title, message: icon.notify(message, title))
    threading.Thread(target=closing_notice, args=(icon,), name="closing-notice", daemon=True).start()
    icon.run()


def closing_notice(icon) -> None:
    """Once ever: when the last TabloView page has been closed, say that TabloView keeps running and
    how to quit it (people expected closing the browser to close TabloView)."""
    while not load_settings().get("closing_notice_shown"):
        time.sleep(30)
        if presence.pages_closed():
            icon.notify("TabloView is still running in the background, keeping your library up to date. "
                        "To close it completely, right-click the TabloView icon by the clock and choose Quit TabloView.",
                        APP_NAME)
            save_settings({"closing_notice_shown": True})


def _fatal(message: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # last-resort visibility for a windowed app
        import traceback
        traceback.print_exc()
        _fatal(f"TabloView hit an unexpected error:\n{e}\n\nDetails: {LOG_DIR / 'tabloview.log'}")
