import asyncio
import time
import unittest

from app import remote


class PhoneRemoteTests(unittest.TestCase):
    def setUp(self):
        remote.reopen()

    def test_a_waiting_screen_gets_a_command_at_once(self):
        async def go():
            waiting = asyncio.create_task(remote.wait_for_commands("screen1", "TV", wait=5))
            await asyncio.sleep(0.05)
            started = time.monotonic()
            remote.send("screen1", "key", "ok")
            got = await waiting
            return got, time.monotonic() - started
        got, took = asyncio.run(go())
        self.assertEqual(got, [{"command": "key", "value": "ok"}])
        self.assertLess(took, 0.5)

    def test_commands_sent_between_requests_wait_for_the_next(self):
        remote.screen("screen1", "TV")
        remote.send("screen1", "key", "up")
        remote.send("screen1", "tune", "S123")
        got = asyncio.run(remote.wait_for_commands("screen1", "TV", wait=5))
        self.assertEqual([c["command"] for c in got], ["key", "tune"])
        self.assertEqual(asyncio.run(remote.wait_for_commands("screen1", "TV", wait=0.1)), [])

    def test_closing_answers_waiting_screens(self):
        # An open wait kept TabloView from closing or restarting (uvicorn waits for every response)
        async def go():
            waiting = asyncio.create_task(remote.wait_for_commands("screen1", "TV", wait=30))
            await asyncio.sleep(0.05)
            started = time.monotonic()
            remote.close_all()
            await waiting
            return time.monotonic() - started
        self.assertLess(asyncio.run(go()), 1.5)

    def test_only_known_commands_and_pages(self):
        remote.screen("screen1", "TV")
        for command, value in (("key", "volume"), ("shell", "x"), ("open", "http://evil"), ("tune", "")):
            with self.assertRaises(remote.RemoteError):
                remote.send("screen1", command, value)
        remote.send("screen1", "open", "#/library")
        with self.assertRaisesRegex(remote.RemoteError, "isn't open"):
            remote.send("nobody", "key", "ok")

    def test_a_screen_that_stopped_asking_is_gone(self):
        clock = [100.0]
        remote.screen("old", "TV", clock=lambda: clock[0])
        remote.set_state("new", "Fire TV", {"page": "Home", "at": 5})
        self.assertEqual({s["id"] for s in remote.listed(now=time.monotonic())}, {"new"})


if __name__ == "__main__":
    unittest.main()
