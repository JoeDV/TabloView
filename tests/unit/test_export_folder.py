import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import database as db
from app.main import app
from app.settings import exports_dir, save_settings

HDR = {"X-TabloView": "1"}


class ExportFolderTests(unittest.TestCase):
    """MP4 exports can go to a folder you choose (only from the PC running TabloView)."""

    def setUp(self):
        db.init_db()
        self.client = TestClient(app, base_url="http://127.0.0.1:7070", client=("127.0.0.1", 50000))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(save_settings, {"export_folder": None})

    def test_choose_a_folder_and_go_back_to_the_default(self):
        default = exports_dir()
        folder = Path(self.tmp.name) / "Tablo exports"  # created if it doesn't exist
        r = self.client.post("/api/system/export_folder", json={"path": str(folder)}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(exports_dir(), folder)
        self.assertTrue(folder.is_dir())
        self.assertEqual(self.client.get("/api/system/info", headers=HDR).json()["downloads_dir"], str(folder))
        self.client.post("/api/system/export_folder", json={"path": None}, headers=HDR)
        self.assertEqual(exports_dir(), default)

    def test_relative_paths_are_refused(self):
        r = self.client.post("/api/system/export_folder", json={"path": "Videos"}, headers=HDR)
        self.assertEqual(r.status_code, 400)

    def test_other_devices_cant_change_it(self):
        remote = TestClient(app, base_url="http://192.168.1.5:7070", client=("192.168.1.20", 50000))
        r = remote.post("/api/system/export_folder", json={"path": self.tmp.name}, headers=HDR)
        self.assertIn(r.status_code, (401, 403))

    def test_exports_made_before_a_change_still_download(self):
        old = Path(self.tmp.name) / "old"
        old.mkdir()
        (old / "Show - S01E01.mp4").write_bytes(b"video")
        db.save_export_job({"job_id": "j1", "filename": "Show - S01E01.mp4", "filepath": str(old / "Show - S01E01.mp4"),
                            "status": "completed", "progress": 100.0, "file_size": 5, "created_at": "2026-10-20T00:00:00Z"})
        self.addCleanup(db.delete_export_job, "j1")
        save_settings({"export_folder": str(Path(self.tmp.name) / "new")})
        r = self.client.get("/downloads/Show - S01E01.mp4")
        self.assertEqual((r.status_code, r.content), (200, b"video"))


if __name__ == "__main__":
    unittest.main()
