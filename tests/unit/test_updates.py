try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import json
import os
import sys
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import updates



class VersionServer:
    """Tiny local HTTP server that serves a version.json."""

    def __init__(self, payload):
        body = json.dumps(payload).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/version.json"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self._version = updates.APP_VERSION
        updates.APP_VERSION = "1.1.1"
        updates._cache.update(checked=0, result=None)

    def tearDown(self):
        updates.APP_VERSION = self._version
        os.environ.pop("TABLOVIEW_UPDATE_URL", None)

    def check(self, url):
        os.environ["TABLOVIEW_UPDATE_URL"] = url
        return asyncio.run(updates.check_for_update(force=True))

    def test_newer_version_is_offered(self):
        dl = "https://github.com/JoeDV/TabloView/releases/tag/v1.2.0"
        srv = VersionServer({"version": "1.2.0", "download_url": dl, "notes": "n"})
        try:
            r = self.check(srv.url)
        finally:
            srv.close()
        self.assertTrue(r["update_available"])
        self.assertEqual((r["latest"], r["download_url"]), ("1.2.0", dl))

    def test_only_tabloviews_github_releases_are_offered(self):
        # A changed version.json (its GitHub account taken over) can't send copies to another download
        for url in ("https://example.com/TabloView-Setup.exe", "javascript:alert(1)", "https://github.com/JoeDV/TabloView.evil.example/x",
                    'https://github.com/JoeDV/TabloView/" onclick="x', "", None):
            self.assertEqual(updates.trusted_download(url), updates.RELEASE_DOWNLOAD_URL, url)
        srv = VersionServer({"version": "1.2.0", "download_url": "https://example.com/dl"})
        try:
            self.assertEqual(self.check(srv.url)["download_url"], updates.RELEASE_DOWNLOAD_URL)
        finally:
            srv.close()

    def test_mac_and_linux_copies_are_told_too(self):
        # They used to get no notice (the download was only the Windows installer); the GitHub
        # release now has all three
        srv = VersionServer({"version": "1.2.0", "download_url": "https://example.com/releases/latest"})
        try:
            for platform in ("linux", "darwin"):
                with mock.patch.object(sys, "platform", platform):
                    r = self.check(srv.url)
                self.assertTrue(r["enabled"] and r["update_available"], platform)
        finally:
            srv.close()

    def test_same_or_older_version_is_up_to_date(self):
        for v in ("1.1.1", "1.0.9"):
            srv = VersionServer({"version": v})
            try:
                self.assertFalse(self.check(srv.url)["update_available"], v)
            finally:
                srv.close()

    def test_unreachable_is_reported_not_raised(self):
        r = self.check("http://127.0.0.1:9/version.json")
        self.assertFalse(r["update_available"])
        self.assertTrue(r["error"])

    def test_version_ordering_is_numeric(self):
        self.assertGreater(updates._version_tuple("1.10.0"), updates._version_tuple("1.9.9"))

    def test_onedrive_links_get_download_flag(self):
        self.assertTrue(updates.direct_download_url("https://1drv.ms/u/c/abc/XYZ?e=1").endswith("download=1"))
        url = "https://gist.githubusercontent.com/x/y/raw/version.json"
        self.assertEqual(updates.direct_download_url(url), url)


if __name__ == "__main__":
    unittest.main()
