try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.routes import devtools

HDR = {"X-TabloView": "1"}


class DevToolsTests(unittest.TestCase):
    """The commercial-marking tool is for development only: off unless TABLOVIEW_DEV_TOOLS=1."""

    def test_off_in_the_app_people_use(self):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.assertEqual(client.get("/dev/marks").status_code, 404)
        self.assertEqual(client.put("/api/dev/marks/ep_1", headers=HDR, json={"marks": []}).status_code, 404)

    def test_marks_are_saved_in_order(self):
        tool = FastAPI()
        tool.include_router(devtools.router)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(devtools, "MARKS_DIR", Path(d)):
            client = TestClient(tool)
            client.put("/api/dev/marks/ep_289676", json={"marks": [{"t": 1027, "kind": "end"}, {"t": 825, "kind": "start"}]})
            self.assertEqual(client.get("/api/dev/marks/ep_289676").json()["marks"],
                             [{"t": 825.0, "kind": "start"}, {"t": 1027.0, "kind": "end"}])
            self.assertEqual(client.get("/api/dev/marks/..%2Fsettings").status_code, 404)


if __name__ == "__main__":
    unittest.main()
