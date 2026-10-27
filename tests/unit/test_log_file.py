import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tabloview


class LogFileTests(unittest.TestCase):
    """tabloview.log starts again past its limit while TabloView runs, not only at start-up (a PC left
    on for weeks grew it without end)."""

    def test_the_log_starts_again_once_past_the_limit(self):
        folder = Path(tempfile.mkdtemp())
        with mock.patch.object(tabloview, "LOG_LIMIT", 1000):
            log = tabloview._LogFile(folder / "tabloview.log")
            for n in range(40):
                print(f"[Test] line {n:03d} " + "x" * 40, file=log)
            log.f.close()
        current = (folder / "tabloview.log").read_text(encoding="utf-8")
        old = (folder / "tabloview.old.log").read_text(encoding="utf-8")
        self.assertLessEqual(len(current.encode()), 1000 + 60)
        self.assertIn("line 039", current)
        self.assertNotIn("line 000", current + old)  # older rounds are gone, not kept for ever
        self.assertIn("line", old)

    def test_a_big_log_is_set_aside_at_start_up(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "tabloview.log").write_text("y" * 3000, encoding="utf-8")
        with mock.patch.object(tabloview, "LOG_LIMIT", 1000):
            log = tabloview._LogFile(folder / "tabloview.log")
            print("fresh", file=log)
            log.f.close()
        self.assertEqual((folder / "tabloview.log").read_text(encoding="utf-8"), "fresh\n")
        self.assertEqual(len((folder / "tabloview.old.log").read_text(encoding="utf-8")), 3000)


if __name__ == "__main__":
    unittest.main()
