"""Unit tests. Run from the project folder:  python -m unittest discover -s tests/unit -t .

Importing this package points TabloView at a throwaway data folder before any app module loads,
so tests never touch your real database, settings, transcode folder or Tablo.
"""
try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

