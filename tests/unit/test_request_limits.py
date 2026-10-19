import asyncio
import unittest
from unittest import mock

import httpx

from app import tablo_client
from app.tablo_client import TabloManager
from tablo_api.models import TabloDevice


class RequestLimitTests(unittest.TestCase):
    """A sync firing dozens of requests at once makes the Tablo stop answering; requests are capped."""

    def test_never_more_than_the_limit_in_flight_and_clicks_dont_wait_for_the_whole_sync(self):
        async def scenario():
            manager = TabloManager.__new__(TabloManager)
            manager.unreachable_since = None
            manager.auth_problems = {}
            manager._local_slots = asyncio.Semaphore(tablo_client.LOCAL_CONCURRENCY)
            manager._bulk_slots = asyncio.Semaphore(tablo_client.BULK_CONCURRENCY)
            manager.device = mock.MagicMock(spec=TabloDevice)
            manager.device.local_url = "http://tablo.test:8887"
            state = {"now": 0, "peak": 0, "order": []}

            async def handler(request):
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
                await asyncio.sleep(0.01)
                state["now"] -= 1
                state["order"].append(request.url.path)
                return httpx.Response(200, json={})

            manager._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with mock.patch("app.tablo_client.TabloAuth.make_device_auth", return_value=("auth", "date")):
                sync = [asyncio.create_task(manager.request_bulk("GET", f"/guide/airings/{i}")) for i in range(40)]
                await asyncio.sleep(0)
                clicks = [asyncio.create_task(manager.request_local("GET", "/server/tuners")) for _ in range(5)]
                await asyncio.gather(*sync, *clicks)
            await manager._http.aclose()
            return state

        state = asyncio.run(scenario())
        self.assertLessEqual(state["peak"], tablo_client.LOCAL_CONCURRENCY)
        last_click = max(i for i, p in enumerate(state["order"]) if p == "/server/tuners")
        self.assertLess(last_click, 15)  # done early, not after all 40 sync requests


if __name__ == "__main__":
    unittest.main()
