try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import subprocess
import unittest
from unittest import mock

from app import netcheck

PLAYLIST = """#EXTM3U
#EXT-X-TARGETDURATION:3
#EXTINF:2.4,
#EXT-X-BYTERANGE:1000@0
segw.ts?abc
#EXTINF:2.4,
#EXT-X-BYTERANGE:1500
segw.ts?abc
#EXT-X-ENDLIST
"""

NETSH = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6E AX211 160MHz
    State                  : connected
    SSID                   : home
    Radio type             : 802.11ax
    Band                   : 5 GHz
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 960
    Signal                 : 96%
"""


class NetCheckTests(unittest.TestCase):
    """Network status: the Tablo's connection, this PC's, and a test of the link between them."""

    def test_a_recordings_pieces_are_byte_ranges_of_one_file(self):
        pieces = netcheck._pieces(PLAYLIST, "http://192.168.1.164/stream/pl.m3u8")
        # The second range leaves out @offset: it starts where the first ended
        self.assertEqual(pieces, [("http://192.168.1.164/stream/segw.ts?abc", (0, 1000)),
                                  ("http://192.168.1.164/stream/segw.ts?abc", (1000, 1500))])

    def test_the_pcs_wifi_signal(self):
        done = subprocess.CompletedProcess([], 0, NETSH.encode(), b"")
        with mock.patch.object(netcheck.subprocess, "run", return_value=done), \
                mock.patch.object(netcheck.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            wifi = netcheck._windows_wifi("Wi-Fi")
        self.assertEqual(wifi, {"ssid": "home", "signal": 96, "band": "5 GHz", "receive_mbps": 1201.0, "transmit_mbps": 960.0})

    def test_no_address_no_lookup(self):
        self.assertEqual(netcheck.pc_connection("not an address"), {"ip": None, "kind": None})


if __name__ == "__main__":
    unittest.main()
