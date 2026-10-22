"""Which H.264 encoder to use for in-browser playback, and the FFmpeg settings for it.

Measured on a 1080i broadcast recording (i7-1165G7, 60 s clip): the old setting (x264 ultrafast,
CRF 28) was visibly blocky (SSIM 0.948); x264 veryfast/CRF 22 and Intel Quick Sync both reach 0.957,
Quick Sync at 6.5x real time (4.1x at 60 fps) without loading the CPU. So: use a graphics-chip
encoder when this PC has one that works, otherwise x264 veryfast.

Each hardware encoder is tried once with a 1-second test encode (cached for the session); one that
fails, here or later on a real stream, is skipped from then on.
"""

import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

from .config import FFMPEG_PATH

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Quick Sync with frames arriving at broadcast pace (from the Tablo) failed with "device failed (-17)"
# within 20-30 s on an i7-1165G7 (Intel driver 30.0.101.1191, 2021); at full speed from a file it
# didn't. With these it ran 2+ minutes of real streams and 12 paced runs without failing, and the
# output is bit-for-bit the same.
QSV_STABLE = ["-async_depth", "1", "-low_power", "0"]

# name -> (label, encoder args at normal quality, args at best quality, pixel format)
HARDWARE = {
    "qsv": ("Intel Quick Sync",
            ["-c:v", "h264_qsv", *QSV_STABLE, "-preset", "veryfast", "-global_quality", "22", "-forced_idr", "1"],
            ["-c:v", "h264_qsv", *QSV_STABLE, "-preset", "medium", "-global_quality", "19", "-forced_idr", "1"], "nv12"),
    "nvenc": ("NVIDIA NVENC",
              ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-forced-idr", "1"],
              ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-forced-idr", "1"], "yuv420p"),
    "amf": ("AMD AMF",
            ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24"],
            ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21"], "yuv420p"),
    # Macs: Apple's encoder (Homebrew's FFmpeg has it). Until 1.2.3 Macs always encoded on the CPU;
    # a 2-hour export took 30 minutes on an M2. A bitrate rather than -q:v, which only Apple Silicon
    # accepts; 8 Mb/s is about what Quick Sync's quality 22 gives for 1080 broadcast TV.
    "videotoolbox": ("Apple VideoToolbox",
                     ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M"],
                     ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-maxrate", "16M", "-bufsize", "24M"], "nv12"),
}
# Which encoders are worth testing where: Apple's only exists on Macs, and the others not there
PLATFORM_ENCODERS = {"darwin": ["videotoolbox"]}
CPU = ("CPU (x264)", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"],
       ["-c:v", "libx264", "-preset", "faster", "-crf", "20"], "yuv420p")
FASTEST = ("CPU (x264, fastest)", ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"], None, "yuv420p")

# MP4 exports aim for a smaller file rather than encoding speed. Measured on a 60 s 1080i recording
# (original broadcast video 3.2 GB/hour): Quick Sync medium/26 gives 2.2 GB/hour at SSIM 0.954
# (playback's veryfast/22 is 3.7 GB/hour, larger than the original); x264 faster/CRF 25 gives
# 2.3 GB/hour at 0.956 but only at about real time. NVENC/AMF values are by analogy, untested.
EXPORT_ARGS = {
    "qsv": ["-c:v", "h264_qsv", *QSV_STABLE, "-preset", "medium", "-global_quality", "26"],
    "nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "26", "-b:v", "0"],
    "amf": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "25", "-qp_p", "27"],
    # About 2.2 GB per hour, like the others
    "videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "5M", "-maxrate", "8M", "-bufsize", "10M"],
    "cpu": ["-c:v", "libx264", "-preset", "faster", "-crf", "25"],
}

_working: Optional[List[str]] = None
_failed: set = set()
_lock = threading.Lock()


def _test(name: str) -> bool:
    _, args, _, pix = HARDWARE[name]
    cmd = [FFMPEG_PATH, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", "testsrc2=size=1920x1080:rate=30", "-t", "1", *args, "-pix_fmt", pix, "-f", "null", "-"]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW).returncode == 0
    except Exception:
        return False


def candidates(platform: str = sys.platform) -> List[str]:
    """The hardware encoders to test on this kind of computer, in preference order."""
    if platform in PLATFORM_ENCODERS:
        return PLATFORM_ENCODERS[platform]
    return [n for n in HARDWARE if n not in {e for names in PLATFORM_ENCODERS.values() for e in names}]


def detect() -> List[str]:
    """Hardware encoders that work on this PC (tested once, in preference order)."""
    global _working
    with _lock:
        if _working is None:
            # TABLOVIEW_NO_HW_ENCODE=1 forces CPU encoding (troubleshooting)
            _working = [] if os.getenv("TABLOVIEW_NO_HW_ENCODE") else [n for n in candidates() if _test(n)]
            print(f"[Encoders] Hardware H.264 encoders: {', '.join(HARDWARE[n][0] for n in _working) or 'none'}")
        return [n for n in _working if n not in _failed]


def mark_failed(name: str) -> None:
    if name in HARDWARE:
        _failed.add(name)
        print(f"[Encoders] {HARDWARE[name][0]} failed on a stream; using the next option from now on")


def choose(quality: str = "auto") -> Dict[str, Any]:
    """{'name', 'label', 'hardware', 'args', 'pix_fmt'} for quality 'auto', 'best' or 'fastest'."""
    if quality == "fastest":
        label, args, _, pix = FASTEST
        return {"name": "fastest", "label": label, "hardware": False, "args": args, "pix_fmt": pix}
    best = quality == "best"
    hw = detect()
    if hw:
        label, normal, high, pix = HARDWARE[hw[0]]
        return {"name": hw[0], "label": label, "hardware": True, "args": high if best else normal, "pix_fmt": pix}
    label, normal, high, pix = CPU
    return {"name": "cpu", "label": label, "hardware": False, "args": high if best else normal, "pix_fmt": pix}


def cpu_fallback(quality: str = "auto") -> Dict[str, Any]:
    label, normal, high, pix = CPU
    return {"name": "cpu", "label": label, "hardware": False,
            "args": high if quality == "best" else normal, "pix_fmt": pix}


def for_export(enc: Dict[str, Any]) -> Dict[str, Any]:
    """The same encoder with the smaller-file export settings."""
    return {**enc, "args": EXPORT_ARGS.get(enc["name"], EXPORT_ARGS["cpu"])}


def detect_in_background() -> None:
    """Run the one-time test at startup so the first playback doesn't wait for it."""
    threading.Thread(target=detect, name="encoder-detect", daemon=True).start()
