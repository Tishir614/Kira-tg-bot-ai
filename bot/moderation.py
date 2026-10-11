from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatPermissions, Message

from bot import log
from bot.sql import AuditLogManager, BlacklistManager, ChatSettingsManager


class ModerationService:
    URL_MARKERS = ("http://", "https://", "t.me/", "www.")

    def __init__(self) -> None:
        self._messages: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def cleanup(self, max_idle_seconds: float = 300.0) -> None:
        now = time.monotonic()
        for key in list(self._messages):
            queue = self._messages[key]
            while queue and now - queue[0] > max_idle_seconds:
                queue.popleft()
            if not queue:
                self._messages.pop(key, None)

    async def inspect(self, message: Message) -> bool:
        """Return True when the message should not continue through user features."""
        if not message.from_user or message.chat.type == "private":
            return False
        user_id = message.from_user.id
        chat_id = message.chat.id
        if await BlacklistManager.is_blocked(user_id, chat_id):
            try:
                await message.delete()
            except Exception:
                pass
            return True

        try:
            member = await message.bot.get_chat_member(chat_id, user_id)
            if member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
                return False
        except Exception:
            pass

        settings = await ChatSettingsManager.get(chat_id)
        text = (message.text or message.caption or "").lower()
        if not settings.links_allowed and any(marker in text for marker in self.URL_MARKERS):
            try:
                await message.delete()
                await message.answer("🔗 Ссылки в этом чате отключены администраторами.")
            except Exception:
                pass
            await AuditLogManager.add(chat_id, 0, "auto_delete_link", target_id=user_id, now=int(time.time()))
            return True

        if not settings.anti_spam:
            return False

        now = time.monotonic()
        key = (chat_id, user_id)
        queue = self._messages[key]
        window = max(2, int(settings.flood_window or 8))
        while queue and now - queue[0] > window:
            queue.popleft()
        queue.append(now)
        limit = max(3, int(settings.flood_limit or 7))
        if len(queue) < limit:
            return False

        queue.clear()
        try:
            await message.delete()
        except Exception:
            pass
        try:
            until = datetime.now(timezone.utc) + timedelta(seconds=60)
            permissions = ChatPermissions(can_send_messages=False)
            await message.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until)
            await message.answer(f"🛡 Пользователь <a href='tg://user?id={user_id}'>получил мут на 60 секунд</a> за флуд.")
        except Exception as exc:
            log.debug("Auto-mute unavailable: %s", exc)
            try:
                await message.answer("🛡 Слишком много сообщений подряд. Антифлуд сработал.")
            except Exception:
                pass
        await AuditLogManager.add(chat_id, 0, "auto_flood", target_id=user_id, now=int(time.time()))
        return True


moderation_service = ModerationService()
