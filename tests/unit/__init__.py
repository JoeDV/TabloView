"""Unit tests. Run from the project folder:  python -m unittest discover -s tests/unit -t .

Importing this package points TabloView at a throwaway data folder before any app module loads,
so tests never touch your real database, settings, transcode folder or Tablo.
"""
import atexit
import os
import shutil
import tempfile

_home = tempfile.mkdtemp(prefix="tabloview-test-")
os.environ["TABLOVIEW_HOME"] = _home
os.environ.pop("TABLOVIEW_UPDATE_URL", None)
atexit.register(shutil.rmtree, _home, ignore_errors=True)
