"""Work started in the background and not waited for (a sync, a guide refresh, a Plex scan...).

asyncio keeps only a weak reference to a task, so one nobody holds can be garbage-collected before it
finishes (Python's documentation for asyncio.create_task). These are held here until they're done."""

import asyncio
from typing import Any, Coroutine, Set

_running: Set[asyncio.Task] = set()


def start(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Run this in the background (from the event loop); returns the task."""
    task = asyncio.get_running_loop().create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)
    return task
