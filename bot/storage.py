from __future__ import annotations

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from bot import log
from bot.config import settings


def create_fsm_storage() -> BaseStorage:
    """Use Redis when configured; otherwise keep zero-config MemoryStorage."""
    if not settings.fsm_redis_url:
        log.info("FSM storage: memory (set FSM_REDIS_URL for persistent/distributed FSM)")
        return MemoryStorage()

    try:
        from aiogram.fsm.storage.redis import RedisStorage
    except ImportError as exc:  # deployment guard
        raise RuntimeError(
            "FSM_REDIS_URL задан, но redis dependency недоступна. Выполни `uv sync`."
        ) from exc

    log.info("FSM storage: Redis")
    return RedisStorage.from_url(settings.fsm_redis_url)
