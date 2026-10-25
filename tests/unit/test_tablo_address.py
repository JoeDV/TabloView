try:
    from . import _test_env  # noqa: F401
except ImportError:
    import _test_env  # noqa: F401

import asyncio
import time
import unittest
from unittest import mock

import httpx

from app.tablo_client import TabloManager
from tablo_api.models import TabloDevice


def manager(url="http://192.168.1.164:8887"):
    m = TabloManager.__new__(TabloManager)
    TabloManager.__init__(m)
    m.device = TabloDevice(sid="SID_1", name="Tablo", local_url=url, lighthouse_token="lh", account_token="acc", client_id="c")
    m.devices = [m.device]
    return m


class TabloAddressTests(unittest.TestCase):
    """The Tablo's address from sign-in went stale when the router gave it another one: TabloView
    said "not responding" for good while Tablo's apps worked. The account knows the current one."""

    def account(self, url):
        return httpx.Response(200, json={"devices": [{"serverId": "SID_9", "url": "http://10.0.0.9:8887"},
                                                     {"serverId": "SID_1", "url": url}]},
                              request=httpx.Request("GET", "https://lighthousetv.ewscloud.com/api/v2/account/"))

    def test_a_moved_tablo_is_followed(self):
        m = manager()
        with mock.patch.object(m._http, "get", return_value=self.account("http://192.168.1.77:8887")) as get, \
                mock.patch.object(m, "save_config") as save:
            self.assertTrue(asyncio.run(m.refresh_address()))
        self.assertEqual(m.device.local_url, "http://192.168.1.77:8887")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer acc")
        save.assert_called_once()

    def test_same_address_changes_nothing(self):
        m = manager()
        with mock.patch.object(m._http, "get", return_value=self.account("http://192.168.1.164:8887")), \
                mock.patch.object(m, "save_config") as save:
            self.assertFalse(asyncio.run(m.refresh_address()))
        save.assert_not_called()

    def test_asked_once_it_has_been_unreachable_a_while(self):
        m = manager()
        m._local_slots = asyncio.Semaphore(1)

        async def go():
            with mock.patch.object(m._http, "request", side_effect=httpx.ConnectError("refused")), \
                    mock.patch.object(m, "refresh_address", new=mock.AsyncMock(return_value=False)) as refresh:
                with self.assertRaises(httpx.ConnectError):
                    await m.request_local("GET", "/server/info")  # just failed: too soon to ask
                m.unreachable_since = time.time() - m.ADDRESS_CHECK_AFTER - 1
                for _ in range(3):
                    with self.assertRaises(httpx.ConnectError):
                        await m.request_local("GET", "/server/info")
                await asyncio.sleep(0)
                return refresh.await_count
        self.assertEqual(asyncio.run(go()), 1)  # then not again for ADDRESS_CHECK_EVERY


if __name__ == "__main__":
    unittest.main()
