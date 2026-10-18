"""Start TabloView (quietly, in the tray) when the user signs in to Windows.

- Regular install: a "TabloView" value under HKCU\\...\\Run that launches TabloView.exe --background.
  Installers before 1.1.4 used a shortcut in the Startup folder instead; it's still recognised, and
  replaced when the setting is changed here.
- Microsoft Store install: the package's startup task (declared in packaging/msix/AppxManifest.xml),
  switched with the WinRT StartupTask API. Registry writes from a packaged app are virtualised, so the
  Run key wouldn't work there. If the user turns it off in Task Manager, only they can turn it back on.
Either way Windows lists TabloView under Task Manager > Startup apps.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

from .config import APP_NAME, IS_PACKAGED, IS_STORE

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
TASK_ID = "TabloViewStartup"
BACKGROUND_ARG = "--background"


def supported() -> bool:
    return IS_PACKAGED and sys.platform == "win32"


def _legacy_shortcut() -> Path:
    return Path(os.getenv("APPDATA") or "") / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"


def _run_value() -> str:
    return f'"{sys.executable}" {BACKGROUND_ARG}'


def _registry_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return _legacy_shortcut().is_file()


def _registry_set(on: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _run_value())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    # Either way the Run value is now the only mechanism
    try:
        _legacy_shortcut().unlink(missing_ok=True)
    except OSError:
        pass


async def _store_task():
    from winrt.windows.applicationmodel import StartupTask
    return await StartupTask.get_async(TASK_ID)


def _store_state(task) -> Dict[str, Any]:
    from winrt.windows.applicationmodel import StartupTaskState
    s = task.state
    return {
        "enabled": s in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY),
        # Turned off in Task Manager (or by an administrator): apps may not switch it back on
        "locked": s in (StartupTaskState.DISABLED_BY_USER, StartupTaskState.DISABLED_BY_POLICY,
                        StartupTaskState.ENABLED_BY_POLICY),
    }


async def get_state() -> Dict[str, Any]:
    if not supported():
        return {"supported": False, "enabled": False, "locked": False}
    try:
        if IS_STORE:
            return {"supported": True, **_store_state(await _store_task())}
        return {"supported": True, "enabled": _registry_enabled(), "locked": False}
    except Exception as e:
        print(f"[Startup] Couldn't read the startup setting: {e}")
        return {"supported": False, "enabled": False, "locked": False, "error": str(e)}


async def set_enabled(on: bool) -> Dict[str, Any]:
    if not supported():
        return await get_state()
    if IS_STORE:
        task = await _store_task()
        if on:
            await task.request_enable_async()
        else:
            task.disable()
    else:
        _registry_set(on)
    return await get_state()


def launched_at_startup() -> bool:
    """True when Windows started TabloView at sign-in (then it stays in the tray, no browser)."""
    if BACKGROUND_ARG in sys.argv[1:]:
        return True
    if IS_STORE:
        try:
            from winrt.windows.applicationmodel import AppInstance
            from winrt.windows.applicationmodel.activation import ActivationKind
            args = AppInstance.get_activated_event_args()
            return args is not None and args.kind == ActivationKind.STARTUP_TASK
        except Exception as e:
            print(f"[Startup] Couldn't read how TabloView was started: {e}")
    return False
