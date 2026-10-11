"""Anti-hang rails for AI requests: bounded queue, bounded wait, per-user backlog limit."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager


class AIBusy(RuntimeError):
    """Raised when the AI is overloaded; callers turn it into a polite 'try again' message."""


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)) or default)))
    except ValueError:
        return default


def queue_cap() -> int:
    return _int("AI_MAX_QUEUE", 6, 1, 100)


def queue_timeout() -> int:
    return _int("AI_QUEUE_TIMEOUT", 90, 5, 900)


def total_timeout() -> int:
    return _int("AI_TOTAL_TIMEOUT", 240, 30, 1800)


def user_backlog_cap() -> int:
    return _int("AI_USER_BACKLOG", 2, 1, 10)


class AdmissionGate:
    def __init__(self) -> None:
        self.waiting = 0

    @asynccontextmanager
    async def slot(self, sem: asyncio.Semaphore):
        """Acquire `sem` but refuse instead of piling up behind a stuck or slow request."""
        if not sem.locked():
            await sem.acquire()
        else:
            if self.waiting >= queue_cap():
                raise AIBusy("Я сейчас отвечаю другим, очередь заполнена. Повтори через минуту.")
            self.waiting += 1
            try:
                await asyncio.wait_for(sem.acquire(), timeout=queue_timeout())
            except asyncio.TimeoutError:
                raise AIBusy("Слишком долго жду очередь на ответ. Повтори чуть позже.") from None
            finally:
                self.waiting -= 1
        try:
            yield
        finally:
            sem.release()
