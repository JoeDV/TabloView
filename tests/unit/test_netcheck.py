try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import json
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



class AccessTests(unittest.TestCase):
    """Network access: Windows Firewall's say per network, and this PC's Tailscale address."""

    WIFI = {"name": "Wi-Fi", "category": "Public"}
    TAILSCALE = {"name": "Tailscale", "category": "Private"}

    def test_allowed_where_a_rule_lets_it_in(self):
        v = netcheck.firewall_verdict([{"action": "Allow", "profile": "Private, Public"}], [self.WIFI, self.TAILSCALE])
        self.assertEqual([n["state"] for n in v], ["allowed", "allowed"])

    def test_a_block_rule_wins(self):
        # Cancel at Windows' question after a Store update: a block rule beside an old allow
        v = netcheck.firewall_verdict([{"action": "Allow", "profile": "Any"}, {"action": "Block", "profile": "Public"}],
                                      [self.WIFI, self.TAILSCALE])
        self.assertEqual([n["state"] for n in v], ["blocked", "allowed"])

    def test_no_rule_for_that_kind_of_network(self):
        v = netcheck.firewall_verdict([{"action": "Allow", "profile": "Private"}], [self.WIFI])
        self.assertEqual(v, [{"network": "Wi-Fi", "category": "Public", "state": "not allowed"}])

    def test_domain_networks(self):
        v = netcheck.firewall_verdict([{"action": "Allow", "profile": "Domain"}], [{"name": "Work", "category": "DomainAuthenticated"}])
        self.assertEqual(v[0]["state"], "allowed")
        self.assertEqual(v[0]["category"], "Domain")

    def tailscale(self, payload):
        netcheck._tailscale.update(value=None, at=float("-inf"))
        self.addCleanup(netcheck._tailscale.update, value=None, at=float("-inf"))
        with mock.patch.object(netcheck.os.path, "isfile", return_value=True),                 mock.patch.object(netcheck.subprocess, "run", return_value=mock.Mock(stdout=json.dumps(payload))):
            return netcheck.tailscale()

    def test_tailscale_name_and_address(self):
        got = self.tailscale({"BackendState": "Running", "Self": {"DNSName": "HPLaptop.tailc0c2e.ts.net.",
                                                                  "TailscaleIPs": ["fd7a::1", "100.123.225.67"]}})
        self.assertEqual(got, {"name": "hplaptop.tailc0c2e.ts.net", "ip": "100.123.225.67"})

    def test_tailscale_stopped(self):
        self.assertIsNone(self.tailscale({"BackendState": "Stopped", "Self": {"DNSName": "x.y.ts.net."}}))

    def test_checking_an_address_never_waits_for_tailscale(self):
        # Every request's address is checked: an old answer is used while a new one is asked for
        import threading
        import time
        netcheck._tailscale.update(value={"name": "old.tailc0c2e.ts.net", "ip": None}, at=float("-inf"))
        self.addCleanup(netcheck._tailscale.update, value=None, at=float("-inf"))
        release = threading.Event()

        def slow(*a, **k):
            release.wait(5)
            return mock.Mock(stdout=json.dumps({"BackendState": "Running", "Self": {"DNSName": "new.tailc0c2e.ts.net."}}))
        with mock.patch.object(netcheck.os.path, "isfile", return_value=True), mock.patch.object(netcheck.subprocess, "run", side_effect=slow):
            started = time.monotonic()
            self.assertEqual(netcheck.tailscale_now()["name"], "old.tailc0c2e.ts.net")
            self.assertEqual(netcheck.tailscale_now()["name"], "old.tailc0c2e.ts.net")  # one lookup at a time
            self.assertLess(time.monotonic() - started, 0.5)
            release.set()
            for _ in range(50):
                if (netcheck.tailscale_now() or {}).get("name") == "new.tailc0c2e.ts.net":
                    break
                time.sleep(0.05)
        self.assertEqual(netcheck.tailscale_now()["name"], "new.tailc0c2e.ts.net")


if __name__ == "__main__":
    unittest.main()
