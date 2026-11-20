try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import ipaddress
import os
import unittest
from unittest import mock

from app import container, lanauth


class EnvSetupTests(unittest.TestCase):
    """A server without a screen (Docker): network access, the PIN and the sign-in from environment variables."""

    def setUp(self):
        self.s = {"allow_lan": False, "lan_pin": None}
        for target in (container, lanauth):
            for p in (mock.patch.object(target, "load_settings", side_effect=lambda: dict(self.s)),
                      mock.patch.object(target, "save_settings", side_effect=lambda u: self.s.update(u))):
                p.start()
                self.addCleanup(p.stop)

    def test_nothing_set_changes_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            container.apply_settings()
        self.assertEqual(self.s, {"allow_lan": False, "lan_pin": None})

    def test_network_and_pin(self):
        with mock.patch.dict(os.environ, {"TABLOVIEW_NETWORK": "1", "TABLOVIEW_PIN": "4321"}, clear=True):
            container.apply_settings()
            self.assertTrue(self.s["allow_lan"])
            self.assertTrue(container.pin_matches("4321"))
            # The same PIN at the next start isn't set again (that signs every device out)
            gen = self.s.get("lan_generation")
            container.apply_settings()
            self.assertEqual(self.s.get("lan_generation"), gen)

    def test_a_bad_pin_is_not_used(self):
        with mock.patch.dict(os.environ, {"TABLOVIEW_PIN": "12ab"}, clear=True):
            container.apply_settings()
        self.assertIsNone(self.s["lan_pin"])

    def test_sign_in_picks_the_named_tablo(self):
        a, b = mock.Mock(sid="SID_A"), mock.Mock(sid="SID_B")
        a.name, b.name = "Den", "Living Room"
        mgr = mock.Mock(is_authenticated=False, device=a)
        mgr.login = mock.AsyncMock(return_value=[a, b])
        with mock.patch("app.config.TABLO_EMAIL", "me@example.com"), mock.patch("app.config.TABLO_PASSWORD", "pw"), \
                mock.patch("app.tablo_client.tablo_manager", mgr), mock.patch.dict(os.environ, {"TABLO_DEVICE": "living room"}):
            asyncio.run(container.sign_in())
        mgr.login.assert_awaited_once_with("me@example.com", "pw")
        mgr.select_device.assert_called_once_with("SID_B")

    def test_no_sign_in_when_signed_in(self):
        mgr = mock.Mock(is_authenticated=True)
        mgr.login = mock.AsyncMock()
        with mock.patch("app.config.TABLO_EMAIL", "me@example.com"), mock.patch("app.config.TABLO_PASSWORD", "pw"), \
                mock.patch("app.tablo_client.tablo_manager", mgr):
            asyncio.run(container.sign_in())
        mgr.login.assert_not_awaited()


class TrustedDeviceTests(unittest.TestCase):
    """TABLOVIEW_ADMIN: home devices that count as this PC, for the settings only it may change."""

    def check(self, listed, address):
        with mock.patch.dict(os.environ, {"TABLOVIEW_ADMIN": listed}):
            return lanauth.trusted_device(ipaddress.ip_address(address))

    def test_listed_addresses_and_ranges(self):
        self.assertTrue(self.check("192.168.1.50", "192.168.1.50"))
        self.assertTrue(self.check("10.0.0.9, 192.168.1.0/24", "192.168.1.77"))
        self.assertFalse(self.check("192.168.1.50", "192.168.1.51"))
        self.assertFalse(self.check("", "192.168.1.50"))
        self.assertFalse(self.check("nonsense", "192.168.1.50"))

    def test_never_from_outside_the_home(self):
        self.assertFalse(self.check("0.0.0.0/0", "8.8.8.8"))
        self.assertFalse(self.check("0.0.0.0/0", "100.101.102.103"))  # Tailscale
        self.assertFalse(self.check("::/0", "fd7a:115c:a1e0::1"))

    def test_counts_as_this_pc(self):
        with mock.patch.dict(os.environ, {"TABLOVIEW_ADMIN": "192.168.1.50"}):
            self.assertTrue(lanauth.is_local("192.168.1.50", {}))
            self.assertFalse(lanauth.is_local("192.168.1.50", {"x-forwarded-for": "1.2.3.4"}))


if __name__ == "__main__":
    unittest.main()
