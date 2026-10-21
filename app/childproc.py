"""FFmpeg processes end when TabloView does, however TabloView ends (closed, crashed, or ended from Task
Manager). Otherwise a leftover FFmpeg keeps reading live TV and holds one of the Tablo's tuners: one
ran for an hour after a restart on 2026-10-20.

Windows: every FFmpeg is put in a job object that kills its processes when the job's last handle
closes, which happens when TabloView's process ends. Linux: the kernel sends FFmpeg SIGKILL when its
parent dies (PR_SET_PDEATHSIG, set at launch through popen_kwargs). macOS has no equivalent.
"""

import subprocess
import sys
from typing import Any, Callable, Dict, Optional

_job: Optional[int] = None


def _windows_job() -> Optional[int]:
    global _job
    if _job is None:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes",
                                                          "WriteBytes", "OtherBytes")]

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        # JobObjectExtendedLimitInformation = 9
        if not kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        _job = job  # kept open for TabloView's lifetime on purpose: closing it ends the processes
    return _job


def tie_to_app(proc: subprocess.Popen) -> None:
    """Make proc end when TabloView ends (Windows; on Linux popen_kwargs does it). Never raises."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(_windows_job()), wintypes.HANDLE(int(proc._handle))):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
    except Exception as e:
        print(f"[Processes] FFmpeg may outlive TabloView if it's ended abruptly: {e}")


def _die_with_parent() -> None:  # runs in the child, before FFmpeg starts (Linux)
    import ctypes
    import signal
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG


def popen_kwargs(preexec: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    """Extra subprocess.Popen arguments: on Linux, FFmpeg is killed if TabloView dies. preexec (e.g.
    lowering priority) still runs, first."""
    if not sys.platform.startswith("linux"):
        return {"preexec_fn": preexec} if preexec else {}

    def both() -> None:
        if preexec:
            preexec()
        _die_with_parent()
    return {"preexec_fn": both}
