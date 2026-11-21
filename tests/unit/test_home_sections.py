try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import re
import typing
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes.system import HomeSection

APP_JS = Path(__file__).resolve().parents[2] / "static" / "app.js"


class HomeSectionTests(unittest.TestCase):
    """Customize on Home saves every section's id: one the server doesn't know made every save fail
    (1.4.1 added Guide alerts to the page but not here)."""

    def test_server_knows_every_section_on_the_page(self):
        block = re.search(r"const HOME_SECTIONS = \[(.*?)\];", APP_JS.read_text(encoding="utf-8"), re.S).group(1)
        page = re.findall(r"\['([a-z]+)', '", block)
        self.assertEqual(list(typing.get_args(HomeSection)), page)

    def test_saving_a_layout_with_every_section(self):
        client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        ids = list(typing.get_args(HomeSection))
        r = client.post("/api/settings", json={"home_order": ids, "home_hidden": ["onnow"]}, headers={"X-TabloView": "1"})
        self.assertEqual(r.status_code, 200, r.text)
        client.post("/api/settings", json={"home_order": [], "home_hidden": []}, headers={"X-TabloView": "1"})


if __name__ == "__main__":
    unittest.main()
