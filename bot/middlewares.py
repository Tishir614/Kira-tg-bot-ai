from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings
from bot.command_aliases import rewrite_command_text
from bot.owners import is_owner


class RussianCommandAliasMiddleware(BaseMiddleware):
    """Make Cyrillic slash commands first-class without touching legacy handlers.

    Telegram Bot API only lets bots publish Latin command names in setMyCommands,
    but aiogram can still route user-typed Cyrillic slash commands. We rewrite the
    command token before filters are evaluated and leave every old handler intact.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            rewritten = rewrite_command_text(event.text)
            if rewritten != event.text:
                event = event.model_copy(update={"text": rewritten})
        return await handler(event, data)


russian_command_alias_middleware = RussianCommandAliasMiddleware()


class RequestRateLimitMiddleware(BaseMiddleware):
    """Small in-process abuse guard for updates.

    This is intentionally generous and protects CPU/network-heavy handlers from a
    single user flooding the dispatcher. Group anti-spam remains a separate feature.
    With multiple replicas use an upstream/Redis rate limiter if strict global limits
    are required.
    """

    def __init__(self) -> None:
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._last_notice: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.is_bot or (is_owner(user.id)):
            return await handler(event, data)

        now = time.monotonic()
        queue = self._events[user.id]
        window = float(settings.request_window_seconds)
        while queue and now - queue[0] > window:
            queue.popleft()
        queue.append(now)

        if len(queue) <= settings.request_limit:
            return await handler(event, data)

        # Prevent the warning itself from becoming spam.
        last = self._last_notice.get(user.id, 0.0)
        if now - last >= window:
            self._last_notice[user.id] = now
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("Слишком много запросов. Попробуй чуть позже.", show_alert=False)
                elif isinstance(event, Message):
                    await event.reply("⏳ Слишком много запросов подряд. Попробуй через несколько секунд.")
            except Exception:
                pass
        return None

    def cleanup(self) -> None:
        cutoff = time.monotonic() - float(settings.request_window_seconds) * 4
        for user_id in list(self._events):
            queue = self._events[user_id]
            while queue and queue[0] < cutoff:
                queue.popleft()
            if not queue:
                self._events.pop(user_id, None)
                self._last_notice.pop(user_id, None)


request_rate_limit = RequestRateLimitMiddleware()
