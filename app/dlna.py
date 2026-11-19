"""The Tablo's antenna channels as a DLNA (UPnP) media server, beside the HDHomeRun-style tuner
(app/tuner.py), for players that browse the home network instead: Roku Media Player, VLC, Kodi,
smart TVs (a forum suggestion, 2026-11-19: a real HDHomeRun shows up in Roku Media Player this way).

It answers on the tuner's port and only while the tuner is on:
  /dlna/device.xml                  what TabloView is (a MediaServer) and its two services
  /dlna/cds.xml, /dlna/cms.xml      the services' descriptions
  /dlna/control/cds|cms             their SOAP actions (Browse is the one players use)
  /dlna/ch/<number>.ts              a channel, the same stream as /auto/v<number>

and announces itself over SSDP (UDP 1900, multicast 239.255.255.250), the way players find media
servers without typing an address. It lists one folder, Live TV, with each channel and what's on it
now: no guide, no recordings. The
channels are converted to H.264 for these players (most Rokus can't play the broadcast's MPEG-2). Only this PC and the home network get an answer, as with the tuner.
"""

import asyncio
import contextlib
import os
import random
import socket
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from fastapi import Request
from fastapi.responses import FileResponse, Response

from . import tuner
from .config import APP_VERSION, STATIC_DIR
from .netcheck import _local_ip, away_from_home

SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900
MAX_AGE = 1800
NOTIFY_SECONDS = 300  # announced again every 5 minutes (players forget a server after MAX_AGE)
NOW_SECONDS = 60  # what's on now, kept a minute
SERVER = f"Windows/10 UPnP/1.0 TabloView/{APP_VERSION}"
DEVICE = "urn:schemas-upnp-org:device:MediaServer:1"
CDS = "urn:schemas-upnp-org:service:ContentDirectory:1"
CMS = "urn:schemas-upnp-org:service:ConnectionManager:1"
MIME = "video/mpeg"
# Streaming, no seeking (it's live), DLNA 1.5
FEATURES = "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=8D100000000000000000000000000000"

_now: Dict[str, Any] = {"at": 0.0, "titles": {}}
_ssdp: Dict[str, Any] = {"transport": None, "task": None, "error": None, "port": None}


def udn() -> str:
    return f"uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'tabloview-dlna-' + tuner.device_id())}"


def targets() -> List[Tuple[str, str]]:
    """(NT/ST, USN) for each thing announced."""
    u = udn()
    return [("upnp:rootdevice", f"{u}::upnp:rootdevice"), (u, u), (DEVICE, f"{u}::{DEVICE}"),
            (CDS, f"{u}::{CDS}"), (CMS, f"{u}::{CMS}")]


# --- Descriptions ---

@tuner.app.get("/dlna/device.xml")
async def device_xml(request: Request):
    base = tuner.base_url(request)
    services = "".join(f"""
      <service>
        <serviceType>{st}</serviceType>
        <serviceId>urn:upnp-org:serviceId:{sid}</serviceId>
        <SCPDURL>/dlna/{short}.xml</SCPDURL>
        <controlURL>/dlna/control/{short}</controlURL>
        <eventSubURL>/dlna/event/{short}</eventSubURL>
      </service>""" for st, sid, short in ((CDS, "ContentDirectory", "cds"), (CMS, "ConnectionManager", "cms")))
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0" xmlns:dlna="urn:schemas-dlna-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <URLBase>{escape(base)}</URLBase>
  <device>
    <deviceType>{DEVICE}</deviceType>
    <dlna:X_DLNADOC>DMS-1.50</dlna:X_DLNADOC>
    <friendlyName>TabloView</friendlyName>
    <manufacturer>TabloView</manufacturer>
    <modelName>TabloView</modelName>
    <modelDescription>Your Tablo's antenna channels</modelDescription>
    <modelNumber>{APP_VERSION}</modelNumber>
    <serialNumber>{tuner.device_id()}</serialNumber>
    <UDN>{udn()}</UDN>
    <iconList>
      <icon><mimetype>image/png</mimetype><width>256</width><height>256</height><depth>24</depth><url>/dlna/icon.png</url></icon>
    </iconList>
    <serviceList>{services}
    </serviceList>
  </device>
</root>
"""
    return Response(xml, media_type="text/xml; charset=utf-8")


@tuner.app.get("/dlna/icon.png")
async def icon():
    return FileResponse(STATIC_DIR / "icon-256.png", media_type="image/png")


def _scpd(actions: Dict[str, List[Tuple[str, str, str]]], variables: List[Tuple[str, str, Optional[List[str]]]]) -> str:
    acts = "".join(
        f"<action><name>{name}</name><argumentList>"
        + "".join(f"<argument><name>{a}</name><direction>{d}</direction><relatedStateVariable>{v}</relatedStateVariable></argument>"
                  for a, d, v in args)
        + "</argumentList></action>" for name, args in actions.items())
    vars_ = "".join(
        f'<stateVariable sendEvents="{"yes" if n in ("SystemUpdateID", "SourceProtocolInfo", "SinkProtocolInfo", "CurrentConnectionIDs") else "no"}">'
        f"<name>{n}</name><dataType>{t}</dataType>"
        + (f"<allowedValueList>{''.join(f'<allowedValue>{v}</allowedValue>' for v in allowed)}</allowedValueList>" if allowed else "")
        + "</stateVariable>" for n, t, allowed in variables)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<scpd xmlns="urn:schemas-upnp-org:service-1-0">'
            f"<specVersion><major>1</major><minor>0</minor></specVersion><actionList>{acts}</actionList>"
            f"<serviceStateTable>{vars_}</serviceStateTable></scpd>\n")


CDS_SCPD = _scpd({
    "Browse": [("ObjectID", "in", "A_ARG_TYPE_ObjectID"), ("BrowseFlag", "in", "A_ARG_TYPE_BrowseFlag"),
               ("Filter", "in", "A_ARG_TYPE_Filter"), ("StartingIndex", "in", "A_ARG_TYPE_Index"),
               ("RequestedCount", "in", "A_ARG_TYPE_Count"), ("SortCriteria", "in", "A_ARG_TYPE_SortCriteria"),
               ("Result", "out", "A_ARG_TYPE_Result"), ("NumberReturned", "out", "A_ARG_TYPE_Count"),
               ("TotalMatches", "out", "A_ARG_TYPE_Count"), ("UpdateID", "out", "A_ARG_TYPE_UpdateID")],
    "GetSearchCapabilities": [("SearchCaps", "out", "SearchCapabilities")],
    "GetSortCapabilities": [("SortCaps", "out", "SortCapabilities")],
    "GetSystemUpdateID": [("Id", "out", "SystemUpdateID")],
}, [("A_ARG_TYPE_ObjectID", "string", None), ("A_ARG_TYPE_BrowseFlag", "string", ["BrowseMetadata", "BrowseDirectChildren"]),
    ("A_ARG_TYPE_Filter", "string", None), ("A_ARG_TYPE_Index", "ui4", None), ("A_ARG_TYPE_Count", "ui4", None),
    ("A_ARG_TYPE_SortCriteria", "string", None), ("A_ARG_TYPE_Result", "string", None),
    ("A_ARG_TYPE_UpdateID", "ui4", None), ("SearchCapabilities", "string", None), ("SortCapabilities", "string", None),
    ("SystemUpdateID", "ui4", None)])

CMS_SCPD = _scpd({
    "GetProtocolInfo": [("Source", "out", "SourceProtocolInfo"), ("Sink", "out", "SinkProtocolInfo")],
    "GetCurrentConnectionIDs": [("ConnectionIDs", "out", "CurrentConnectionIDs")],
    "GetCurrentConnectionInfo": [("ConnectionID", "in", "A_ARG_TYPE_ConnectionID"), ("RcsID", "out", "A_ARG_TYPE_RcsID"),
                                 ("AVTransportID", "out", "A_ARG_TYPE_AVTransportID"), ("ProtocolInfo", "out", "A_ARG_TYPE_ProtocolInfo"),
                                 ("PeerConnectionManager", "out", "A_ARG_TYPE_ConnectionManager"),
                                 ("PeerConnectionID", "out", "A_ARG_TYPE_ConnectionID"), ("Direction", "out", "A_ARG_TYPE_Direction"),
                                 ("Status", "out", "A_ARG_TYPE_ConnectionStatus")],
}, [("SourceProtocolInfo", "string", None), ("SinkProtocolInfo", "string", None), ("CurrentConnectionIDs", "string", None),
    ("A_ARG_TYPE_ConnectionID", "i4", None), ("A_ARG_TYPE_RcsID", "i4", None), ("A_ARG_TYPE_AVTransportID", "i4", None),
    ("A_ARG_TYPE_ProtocolInfo", "string", None), ("A_ARG_TYPE_ConnectionManager", "string", None),
    ("A_ARG_TYPE_Direction", "string", ["Input", "Output"]),
    ("A_ARG_TYPE_ConnectionStatus", "string", ["OK", "ContentFormatMismatch", "InsufficientBandwidth", "UnreliableChannel", "Unknown"])])


@tuner.app.get("/dlna/cds.xml")
async def cds_xml():
    return Response(CDS_SCPD, media_type="text/xml; charset=utf-8")


@tuner.app.get("/dlna/cms.xml")
async def cms_xml():
    return Response(CMS_SCPD, media_type="text/xml; charset=utf-8")


@tuner.app.api_route("/dlna/event/{service}", methods=["SUBSCRIBE", "UNSUBSCRIBE"])
async def event(service: str, request: Request):
    """Players subscribe to changes; there are none to send (the channel list hardly changes)."""
    if request.method == "UNSUBSCRIBE":
        return Response(status_code=200)
    return Response(status_code=200, headers={"SID": request.headers.get("sid") or f"uuid:{uuid.uuid4()}",
                                              "TIMEOUT": "Second-1800", "Server": SERVER})


# --- Browsing: a Live TV folder with the channels ---

def now_titles(chans: List[Dict[str, Any]], airings: List[Dict[str, Any]]) -> Dict[str, str]:
    """Channel number → the show on it now."""
    by_id = {c["id"]: c for c in chans}
    by_call = {c["call_sign"].upper(): c for c in chans if c["call_sign"]}
    found = {}
    for a in airings:
        c = by_id.get(a.get("channel_identifier")) or by_call.get((a.get("channel_call_sign") or "").upper())
        if c and a.get("show_title"):
            found.setdefault(c["number"], a["show_title"])
    return found


async def _on_now(chans: List[Dict[str, Any]]) -> Dict[str, str]:
    if time.time() - _now["at"] >= NOW_SECONDS:
        try:
            _now.update(titles=now_titles(chans, await asyncio.to_thread(tuner.guide_airings, 0)), at=time.time())
        except Exception as e:
            print(f"[DLNA] Couldn't read what's on: {e}")
    return _now["titles"]


def _container(oid: str, parent: str, title: str, count: int) -> str:
    return (f'<container id="{oid}" parentID="{parent}" restricted="1" searchable="0" childCount="{count}">'
            f"<dc:title>{escape(title)}</dc:title><upnp:class>object.container.storageFolder</upnp:class></container>")


def _item(c: Dict[str, Any], base: str, on_now: str = "") -> str:
    title = f"{c['number']} {c['name']}" + (f" · {on_now}" if on_now else "")
    logo = f"<upnp:albumArtURI>{escape(c['logo'])}</upnp:albumArtURI>" if c.get("logo") else ""
    desc = f"<dc:description>{escape(on_now)}</dc:description>" if on_now else ""
    return (f'<item id="ch-{escape(c["number"])}" parentID="live" restricted="1">'
            f"<dc:title>{escape(title)}</dc:title><upnp:class>object.item.videoItem.videoBroadcast</upnp:class>"
            f"<upnp:channelName>{escape(c['name'])}</upnp:channelName>{desc}{logo}"
            f'<res protocolInfo="http-get:*:{MIME}:{FEATURES}">{escape(base)}/dlna/ch/{escape(c["number"])}.ts</res></item>')


def didl(parts: List[str]) -> str:
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">' + "".join(parts) + "</DIDL-Lite>")


async def browse(object_id: str, flag: str, start: int, count: int, base: str) -> Optional[Tuple[str, int, int]]:
    """(DIDL-Lite result, number returned, total matches), or None for an unknown object."""
    chans = await tuner.lineup()
    if object_id == "0":
        if flag == "BrowseMetadata":
            return didl([_container("0", "-1", "TabloView", 1)]), 1, 1
        parts = [_container("live", "0", "Live TV", len(chans))]
    elif object_id == "live":
        if flag == "BrowseMetadata":
            return didl([_container("live", "0", "Live TV", len(chans))]), 1, 1
        on_now = await _on_now(chans)
        parts = [_item(c, base, on_now.get(c["number"], "")) for c in chans]
    elif object_id.startswith("ch-"):
        c = next((c for c in chans if c["number"] == object_id[3:]), None)
        if not c:
            return None
        if flag == "BrowseMetadata":
            return didl([_item(c, base, (await _on_now(chans)).get(c["number"], ""))]), 1, 1
        parts = []
    else:
        return None
    page = parts[start:start + count] if count else parts[start:]
    return didl(page), len(page), len(parts)


def _soap(service: str, action: str, out: Dict[str, Any]) -> Response:
    args = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in out.items())
    body = ('<?xml version="1.0" encoding="utf-8"?>\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action}Response xmlns:u="{service}">{args}</u:{action}Response></s:Body></s:Envelope>')
    return Response(body, media_type='text/xml; charset="utf-8"', headers={"Server": SERVER})


def _fault(code: int, text: str) -> Response:
    body = ('<?xml version="1.0" encoding="utf-8"?>\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><s:Fault>'
            "<faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring><detail>"
            f'<UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>{code}</errorCode>'
            f"<errorDescription>{escape(text)}</errorDescription></UPnPError></detail></s:Fault></s:Body></s:Envelope>")
    return Response(body, status_code=500, media_type='text/xml; charset="utf-8"')


def _soap_args(body: bytes) -> Dict[str, str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {}
    for el in root.iter():
        if el.tag.split("}")[-1] == "Body" and len(el):
            return {a.tag.split("}")[-1]: (a.text or "") for a in el[0]}
    return {}


def _int(v: Optional[str]) -> int:
    try:
        return max(int(v or 0), 0)
    except ValueError:
        return 0


@tuner.app.post("/dlna/control/{service}")
async def control(service: str, request: Request):
    action = (request.headers.get("soapaction") or "").strip().strip('"').rsplit("#", 1)[-1]
    args = _soap_args(await request.body())
    if service == "cds":
        if action == "Browse":
            got = await browse(args.get("ObjectID", "0"), args.get("BrowseFlag", "BrowseDirectChildren"),
                               _int(args.get("StartingIndex")), _int(args.get("RequestedCount")), tuner.base_url(request))
            if got is None:
                return _fault(701, "No such object")
            result, returned, total = got
            return _soap(CDS, action, {"Result": result, "NumberReturned": returned, "TotalMatches": total, "UpdateID": 1})
        if action == "GetSearchCapabilities":
            return _soap(CDS, action, {"SearchCaps": ""})
        if action == "GetSortCapabilities":
            return _soap(CDS, action, {"SortCaps": ""})
        if action == "GetSystemUpdateID":
            return _soap(CDS, action, {"Id": 1})
    elif service == "cms":
        if action == "GetProtocolInfo":
            return _soap(CMS, action, {"Source": f"http-get:*:{MIME}:{FEATURES}", "Sink": ""})
        if action == "GetCurrentConnectionIDs":
            return _soap(CMS, action, {"ConnectionIDs": "0"})
        if action == "GetCurrentConnectionInfo":
            return _soap(CMS, action, {"RcsID": -1, "AVTransportID": -1, "ProtocolInfo": "", "PeerConnectionManager": "",
                                       "PeerConnectionID": -1, "Direction": "Output", "Status": "OK"})
    return _fault(401, "Invalid action")


# --- The stream: the tuner's, with the headers DLNA players look for ---

STREAM_HEADERS = {"transferMode.dlna.org": "Streaming", "contentFeatures.dlna.org": FEATURES, "Server": SERVER}


@tuner.app.api_route("/dlna/ch/{number}.ts", methods=["GET", "HEAD"])
async def channel(number: str, request: Request):
    if request.method == "HEAD":  # players ask first: answer without tuning anything
        if not any(c["number"] == number for c in await tuner.lineup()):
            return Response(status_code=404)
        return Response(status_code=200, media_type=MIME, headers=STREAM_HEADERS)
    # Converted to H.264: the Tablo's MPEG-2 doesn't play on most Rokus (VLC, Kodi and TVs would
    # manage, but a player can't say which it wants)
    resp = await tuner.channel_stream(number, request, convert=True)
    resp.headers.update(STREAM_HEADERS)
    resp.headers["content-type"] = MIME
    return resp


# --- Announcing: SSDP ---

def search_reply(st: str, location: str) -> List[str]:
    """The answers to an M-SEARCH for st ('ssdp:all' gets one per target)."""
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    return [f"HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age={MAX_AGE}\r\nDATE: {date}\r\nEXT:\r\nLOCATION: {location}\r\n"
            f"SERVER: {SERVER}\r\nST: {nt}\r\nUSN: {usn}\r\nContent-Length: 0\r\n\r\n"
            for nt, usn in targets() if st in ("ssdp:all", nt)]


def notify(nts: str, location: str) -> List[str]:
    """NOTIFY messages: nts is 'ssdp:alive' or 'ssdp:byebye'."""
    alive = nts == "ssdp:alive"
    return [f"NOTIFY * HTTP/1.1\r\nHOST: {SSDP_GROUP}:{SSDP_PORT}\r\n"
            + (f"CACHE-CONTROL: max-age={MAX_AGE}\r\nLOCATION: {location}\r\nSERVER: {SERVER}\r\n" if alive else "")
            + f"NT: {nt}\r\nNTS: {nts}\r\nUSN: {usn}\r\n\r\n" for nt, usn in targets()]


def parse_search(data: bytes) -> Optional[Tuple[str, int]]:
    """(ST, MX) of an M-SEARCH, else None."""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    if not lines or not lines[0].upper().startswith("M-SEARCH"):
        return None
    headers = {}
    for line in lines[1:]:
        k, sep, v = line.partition(":")
        if sep:
            headers[k.strip().upper()] = v.strip()
    if headers.get("MAN", "").strip('"') != "ssdp:discover" or not headers.get("ST"):
        return None
    return headers["ST"], _int(headers.get("MX"))


def _location(ip: str) -> str:
    return f"http://{ip}:{_ssdp['port']}/dlna/device.xml"


def _home_ips() -> List[str]:
    """This PC's IPv4 addresses on home networks (not Tailscale's, not loopback)."""
    ips = set()
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    guess = _local_ip("192.168.1.1")
    if guess:
        ips.add(guess)
    return sorted(ip for ip in ips if not ip.startswith("127.") and not away_from_home(ip))


class _Responder(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        found = parse_search(data)
        if not found or away_from_home(addr[0]):
            return
        st, mx = found
        replies = search_reply(st, _location(_local_ip(addr[0]) or addr[0]))
        if replies:
            asyncio.get_running_loop().call_later(random.uniform(0, min(max(mx, 1), 3)) * 0.5, self._send, replies, addr)

    def _send(self, replies, addr):
        for r in replies:
            with contextlib.suppress(OSError):
                self.transport.sendto(r.encode(), addr)


def _listen_socket(ips: List[str]) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Windows' own SSDP service listens there too
    sock.bind(("", SSDP_PORT))
    joined = False
    for ip in ips:
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(SSDP_GROUP) + socket.inet_aton(ip))
            joined = True
    if not joined:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(SSDP_GROUP) + socket.inet_aton("0.0.0.0"))
    sock.setblocking(False)
    return sock


def _announce(nts: str) -> None:
    for ip in _home_ips():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                s.bind((ip, 0))
                for msg in notify(nts, _location(ip)):
                    s.sendto(msg.encode(), (SSDP_GROUP, SSDP_PORT))
        except OSError as e:
            print(f"[DLNA] Couldn't announce on {ip}: {e}")


async def _announcer() -> None:
    while True:
        await asyncio.to_thread(_announce, "ssdp:alive")
        await asyncio.sleep(NOTIFY_SECONDS)


async def start(port: int) -> None:
    """Start announcing (with the tuner). A developer copy whose tuner answers only this PC skips it."""
    if _ssdp["transport"] or (os.getenv("TABLOVIEW_TUNER_HOST") or "0.0.0.0") not in ("0.0.0.0", ""):
        return
    _ssdp.update(port=port, error=None)
    try:
        sock = _listen_socket(_home_ips())
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(_Responder, sock=sock)
    except OSError as e:
        _ssdp["error"] = str(e)
        print(f"[DLNA] Couldn't listen for players: {e}")
        return
    _ssdp.update(transport=transport, task=asyncio.create_task(_announcer()))
    print("[DLNA] Announcing TabloView to players on the home network")


async def stop() -> None:
    task, transport = _ssdp.get("task"), _ssdp.get("transport")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if transport:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_announce, "ssdp:byebye")
        transport.close()
    _ssdp.update(transport=None, task=None)


def status() -> Dict[str, Any]:
    return {"announcing": bool(_ssdp.get("transport")), "error": _ssdp.get("error")}
