"""Serialize memory updates per conversation without retaining idle locks."""
import asyncio
from contextlib import asynccontextmanager

class ConversationLocks:
    def __init__(self):
        self._entries = {}

    @asynccontextmanager
    async def hold(self, key):
        lock, count = self._entries.get(key, (asyncio.Lock(), 0))
        self._entries[key] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            remaining = self._entries[key][1] - 1
            if remaining:
                self._entries[key] = (lock, remaining)
            else:
                self._entries.pop(key, None)
