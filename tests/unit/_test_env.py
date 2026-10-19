"""Test environment initialization.

Ensures that tests always run with TABLOVIEW_HOME pointing to a throwaway temporary directory,
preventing unit tests from reading or mutating the real database, credentials, or physical Tablo device.
"""
import atexit
import os
import shutil
import tempfile

if "TABLOVIEW_HOME" not in os.environ:
    _home = tempfile.mkdtemp(prefix="tabloview-test-")
    os.environ["TABLOVIEW_HOME"] = _home
    os.environ.pop("TABLOVIEW_UPDATE_URL", None)
    atexit.register(shutil.rmtree, _home, ignore_errors=True)
