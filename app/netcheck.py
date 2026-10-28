"""Network status (Settings → Desktop & network): how the Tablo says it's connected, how this PC is,
and a test of the link between them, response time and how fast a recording arrives, so "it keeps
pausing" can be told apart from a slow PC."""

import asyncio
import ipaddress
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from .database import get_connection

# 1080 antenna TV as the Tablo sends it is about 19 Mb/s (2.4 MB/s); a stream needs that much,
# steadily, from the Tablo to this PC
HD_MB_PER_S = 2.5
TEST_SECONDS = 8  # read a recording at full speed for this long...
TEST_MAX_BYTES = 80 * 1024 * 1024  # ...or this much, whichever comes first
PING_COUNT = 5

_test_lock = asyncio.Lock()


async def tablo_network() -> Optional[Dict[str, Any]]:
    """The Tablo's own report: connection ("ethernet" or "wifi"), status, ip, and whatever else it
    gives (a Tablo on Wi-Fi may report its signal; the one this was built on is wired)."""
    from .tablo_client import tablo_manager
    try:
        r = await tablo_manager.request_local("GET", "/server/network")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[Network] Couldn't read the Tablo's network status: {e}")
        return None


def _local_ip(towards: str) -> Optional[str]:
    """This PC's address on the way to the Tablo (a UDP connect sends nothing)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((towards, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def _windows_adapter(ip: str) -> Dict[str, Any]:
    """Windows: the network adapter with that address, and its Wi-Fi details when it's wireless."""
    script = (
        "$a = Get-NetIPAddress -IPAddress $env:TABLOVIEW_IP -ErrorAction SilentlyContinue | Get-NetAdapter -ErrorAction SilentlyContinue; "
        "if ($a) { @{name=$a.Name; description=$a.InterfaceDescription; media=[string]$a.PhysicalMediaType; "
        "link=[string]$a.LinkSpeed} | ConvertTo-Json -Compress }")
    out: Dict[str, Any] = {}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=15,
                           env={**os.environ, "TABLOVIEW_IP": ip}, creationflags=subprocess.CREATE_NO_WINDOW)
        text = r.stdout.decode("utf-8", errors="replace").strip()
        out = json.loads(text) if text else {}
    except Exception as e:
        print(f"[Network] Couldn't read this PC's network adapter: {e}")
    wireless = "802.11" in (out.get("media") or "") or "wi-fi" in (out.get("description") or "").lower() \
        or "wireless" in (out.get("description") or "").lower()
    result: Dict[str, Any] = {"kind": "wifi" if wireless else ("ethernet" if out else None),
                              "adapter": out.get("name"), "link_speed": out.get("link") or None}
    if wireless:
        result["wifi"] = _windows_wifi(out.get("name"))
    return result


def _windows_wifi(adapter: Optional[str]) -> Optional[Dict[str, Any]]:
    """The Wi-Fi connection's signal, network name, band and speeds (netsh wlan show interfaces)."""
    try:
        r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        text = r.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None
    # One block per wireless adapter, each starting at its "Name" line
    blocks = re.split(r"\n(?=\s*Name\s*:)", "\n" + text)
    for block in blocks:
        fields = {k.strip().lower(): v.strip() for k, v in re.findall(r"^\s*([^:\n]+?)\s*:\s*(.+)$", block, re.M)}
        if not fields.get("name") or (adapter and fields["name"] != adapter and len(blocks) > 2):
            continue
        signal = re.match(r"(\d+)", fields.get("signal", ""))
        return {"ssid": fields.get("ssid"), "signal": int(signal.group(1)) if signal else None,
                "band": fields.get("band") or fields.get("radio type"),
                "receive_mbps": _number(fields.get("receive rate (mbps)")),
                "transmit_mbps": _number(fields.get("transmit rate (mbps)"))}
    return None


def _number(text: Optional[str]) -> Optional[float]:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def pc_connection(tablo_ip: Optional[str]) -> Dict[str, Any]:
    """How this PC reaches the Tablo: its address, and on Windows Ethernet or Wi-Fi (with the signal)."""
    try:
        ipaddress.ip_address(tablo_ip or "")
    except ValueError:
        return {"ip": None, "kind": None}
    ip = _local_ip(tablo_ip)
    if not ip:
        return {"ip": None, "kind": None}
    details = _windows_adapter(ip) if sys.platform == "win32" else {"kind": None}
    return {"ip": ip, **details}


async def status() -> Dict[str, Any]:
    from .tablo_client import tablo_manager
    tablo = await tablo_network()
    tablo_ip = (tablo or {}).get("ip") or (tablo_manager.device.local_url.split("//")[-1].split(":")[0]
                                           if tablo_manager.device else None)
    pc = await asyncio.to_thread(pc_connection, tablo_ip)
    return {"tablo": tablo, "pc": pc}


# ---------------------------------------------------------------------------------------------------
# Other devices (network access): this PC's Tailscale address for away from home, and whether Windows
# Firewall lets them in
# ---------------------------------------------------------------------------------------------------
TAILSCALE_CLI = [shutil.which("tailscale"), r"C:\Program Files\Tailscale\tailscale.exe",
                 "/Applications/Tailscale.app/Contents/MacOS/Tailscale"]
_tailscale: Dict[str, Any] = {"value": None, "at": float("-inf")}


def tailscale(max_age: float = 300) -> Optional[Dict[str, str]]:
    """This PC on Tailscale, {"name": "hplaptop.tailc0c2e.ts.net", "ip": "100.x.x.x"}, or None when
    Tailscale isn't installed or running. Asked at most every max_age seconds."""
    if time.monotonic() - _tailscale["at"] > max_age:
        _tailscale["at"] = time.monotonic()
        cli = next((c for c in TAILSCALE_CLI if c and os.path.isfile(c)), None)
        value = None
        if cli:
            try:
                out = subprocess.run([cli, "status", "--json"], capture_output=True, text=True, timeout=5,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                d = json.loads(out)
                me = d.get("Self") or {}
                ip = next((a for a in me.get("TailscaleIPs") or [] if "." in a), None)
                if d.get("BackendState") == "Running" and (me.get("DNSName") or ip):
                    value = {"name": (me.get("DNSName") or "").rstrip(".").lower() or None, "ip": ip}
            except Exception:
                pass
        _tailscale["value"] = value
    return _tailscale["value"]


_tailscale_refreshing = threading.Lock()


def tailscale_now(max_age: float = 300) -> Optional[Dict[str, str]]:
    """tailscale(), without waiting: the last answer, asked again in the background when it's older
    than max_age. For checking every request's address, which mustn't wait up to 5 s for Tailscale."""
    if time.monotonic() - _tailscale["at"] > max_age and _tailscale_refreshing.acquire(blocking=False):
        def refresh():
            try:
                tailscale(max_age)
            finally:
                _tailscale_refreshing.release()
        threading.Thread(target=refresh, name="tailscale-status", daemon=True).start()
    return _tailscale["value"]


_FIREWALL_SCRIPT = (
    "$r = Get-NetFirewallApplicationFilter -Program $env:TABLOVIEW_EXE -ErrorAction SilentlyContinue | Get-NetFirewallRule "
    "| Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' }; "
    "@{rules = @($r | ForEach-Object { @{action = [string]$_.Action; profile = [string]$_.Profile} }); "
    "networks = @(Get-NetConnectionProfile | ForEach-Object { @{name = $_.InterfaceAlias; category = [string]$_.NetworkCategory} })} "
    "| ConvertTo-Json -Compress -Depth 4")


def firewall_verdict(rules: List[Dict[str, str]], networks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Per connected network: "blocked" (a block rule wins over any allow), "allowed", or "not allowed"
    (no rule: Windows drops other devices' connections without asking again)."""
    def covers(profile: str, category: str) -> bool:
        kinds = {p.strip().lower() for p in (profile or "").split(",")}
        cat = "domain" if category.lower().startswith("domain") else category.lower()
        return "any" in kinds or cat in kinds
    out = []
    for n in networks:
        cat = n.get("category") or ""
        if any(r.get("action") == "Block" and covers(r.get("profile", ""), cat) for r in rules):
            state = "blocked"
        elif any(r.get("action") == "Allow" and covers(r.get("profile", ""), cat) for r in rules):
            state = "allowed"
        else:
            state = "not allowed"
        out.append({"network": n.get("name") or "", "category": "Domain" if cat.lower().startswith("domain") else cat, "state": state})
    return out


def firewall() -> Optional[List[Dict[str, str]]]:
    """Windows: whether Windows Firewall lets other devices reach TabloView on each connected network.
    The Store version gets a new rule with each update (its folder changes), and choosing Cancel at
    Windows' question leaves a block rule: network access then stops working without a word."""
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", _FIREWALL_SCRIPT], capture_output=True, timeout=20,
                           env={**os.environ, "TABLOVIEW_EXE": sys.executable}, creationflags=subprocess.CREATE_NO_WINDOW)
        d = json.loads(r.stdout.decode("utf-8", errors="replace").strip() or "{}")
    except Exception as e:
        print(f"[Network] Couldn't read Windows Firewall's rules: {e}")
        return None
    as_list = lambda v: v if isinstance(v, list) else ([v] if v else [])
    return firewall_verdict(as_list(d.get("rules")), as_list(d.get("networks")))


async def access() -> Dict[str, Any]:
    tail, fw = await asyncio.gather(asyncio.to_thread(tailscale, 30), asyncio.to_thread(firewall))
    return {"tailscale": tail, "firewall": fw}


def _pieces(playlist: str, base: str) -> List[Tuple[str, Optional[Tuple[int, int]]]]:
    """(address, (offset, length) or None) of each piece of a media playlist, in order."""
    pieces, rng, ends = [], None, {}
    for line in playlist.splitlines():
        s = line.strip()
        if s.startswith("#EXT-X-BYTERANGE:"):
            length, _, offset = s[17:].partition("@")
            rng = (int(offset) if offset else None, int(length))
        elif s and not s.startswith("#"):
            url = urljoin(base, s)
            if rng:
                start = rng[0] if rng[0] is not None else ends.get(url, 0)
                ends[url] = start + rng[1]
                pieces.append((url, (start, rng[1])))
            else:
                pieces.append((url, None))
            rng = None
    return pieces


async def speed_test() -> Dict[str, Any]:
    """Response time (/ping), and a recording read at full speed for TEST_SECONDS: how fast the
    Tablo can deliver video to this PC. Reading a recording uses no tuner."""
    from .export_pace import something_playing
    from .tablo_client import tablo_manager
    if not tablo_manager.device:
        raise RuntimeError("Not signed in to a Tablo")
    if _test_lock.locked():
        raise RuntimeError("A test is already running")
    async with _test_lock:
        base = tablo_manager.device.local_url.rstrip("/")
        busy = await something_playing()
        async with httpx.AsyncClient(timeout=15) as http:
            times = []
            for _ in range(PING_COUNT):
                t0 = time.perf_counter()
                try:
                    await http.get(f"{base}/ping")
                    times.append((time.perf_counter() - t0) * 1000)
                except httpx.HTTPError:
                    pass
            result: Dict[str, Any] = {"ping_ms": round(statistics.median(times), 1) if times else None,
                                      "ping_lost": PING_COUNT - len(times), "busy": busy}
            with get_connection() as conn:
                row = conn.execute("SELECT path, show_title FROM episodes WHERE path IS NOT NULL "
                                   "ORDER BY air_date DESC LIMIT 1").fetchone()
            if not row:
                result["mb_per_s"] = None
                return result
            watch = await tablo_manager.get_airing_watch_url(row["path"])
            token = watch.get("token")
            try:
                url = watch["playlist_url"]
                text = (await http.get(url)).text
                if "#EXT-X-STREAM-INF" in text:  # a list of versions: take the first
                    variant = next(l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#"))
                    url = urljoin(url, variant)
                    text = (await http.get(url)).text
                got, t0 = 0, time.perf_counter()
                for piece_url, rng in _pieces(text, url):
                    headers = {"Range": f"bytes={rng[0]}-{rng[0] + rng[1] - 1}"} if rng else None
                    async with http.stream("GET", piece_url, headers=headers) as resp:
                        async for chunk in resp.aiter_bytes():
                            got += len(chunk)
                    if time.perf_counter() - t0 >= TEST_SECONDS or got >= TEST_MAX_BYTES:
                        break
                elapsed = time.perf_counter() - t0
            finally:
                await tablo_manager.end_watch_session(token)
        mb = got / (1024 * 1024) / elapsed if elapsed > 0 else 0
        result.update({"mb_per_s": round(mb, 1), "mbit_per_s": round(mb * 8 * 1.048576, 0),
                       "hd_streams": int(mb // HD_MB_PER_S), "tested_with": row["show_title"]})
        print(f"[Network] Test: {result}")
        return result
