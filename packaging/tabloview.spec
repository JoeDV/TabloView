# PyInstaller spec for TabloView (one-folder, windowed). Run via packaging/build.ps1.
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
STAGE = os.path.join(ROOT, 'build', 'stage')  # ffmpeg + icon prepared by build.ps1

a = Analysis(
    [os.path.join(ROOT, 'tabloview.py')],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, 'static'), 'static'),
        (os.path.join(STAGE, 'ffmpeg'), 'ffmpeg'),
        (os.path.join(ROOT, 'LICENSE'), '.'),
    ],
    # uvicorn picks its loop/protocol implementations dynamically; pystray picks its backend
    hiddenimports=collect_submodules('uvicorn') + ['pystray._win32', 'app.main'],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TabloView',
    console=False,
    icon=os.path.join(STAGE, 'tabloview.ico'),
    version=os.path.join(STAGE, 'version_info.txt'),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name='TabloView', upx=False)
