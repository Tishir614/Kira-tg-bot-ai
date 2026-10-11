from __future__ import annotations

import html
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message, TelegramObject

from bot import log
from bot.config import settings
from bot.owners import is_owner
from bot.group_features import GroupRulesSettingsManager, WarningManager
from bot.rules_engine import RuleHit, inspect_text
from bot.sql import AuditLogManager, ChatManager, UserManager


RULES_TEXT = """📌 <b>ПРАВИЛА ЧАТА</b>

Вступая в сообщество, вы соглашаетесь со всеми правилами этого сообщества.

<b>1. Общение</b>
• Запрещены оскорбления участников чата.
• Запрещено разжигание и поддержка конфликтов, даже «в шутку».
• При провокации на конфликт наказание получает провокатор. Степень неадекватного поведения определяет администрация.

<b>1.1. Политика</b>
• Запрещена политика в любом её проявлении: арты, фото, видео, аватарки, политические стикеры, обсуждения и медиаконтент с отсылками к текущим политическим конфликтам между государствами.
• Исключение: исторические обсуждения без оскорблений, если их разрешил модератор.

<b>1.2. Личная информация</b>
• Запрещён деанон участников, публикация личной информации и скриншотов личных переписок.

<b>1.3. Дискриминация</b>
• Запрещены дискриминация, высмеивание и оскорбление участника по взглядам, расе, интересам и вкусам.

<b>1.4. Вера</b>
• Запрещено высмеивание, ущемление и оскорбление любой религии и веры участников чата.

<b>1.5. Стикеры</b>
• Не отправляйте больше 3 стикеров подряд. Исключение: неповторяющаяся сюжетная последовательность.

<b>1.6. Навязчивое внимание</b>
• Запрещено чрезмерное внимание к участнику, если оно создаёт ему или чату дискомфорт.

<b>1.7. Формат общения</b>
• Предпочтителен текст. Если вас просят писать вместо голосовых, желательно прислушаться.

<b>2. Контент</b>
<b>2.1.</b> Разрешён фурри/yiff 18+ контент: арты, GIF и видео.
<b>2.2.</b> Запрещён IRL 18+ контент с реальными людьми. Исключение: материал с предметом фурсьюта.
<b>2.3.</b> Запрещена реклама и пересылка контента из других каналов/групп с сохранённым источником или рекламными ссылками.
<b>2.4.</b> При отправке 5+ файлов группируйте их и используйте сжатый вид.
<b>2.5.</b> Запрещена рассылка вредоносного контента в чате и личных сообщениях.
<b>2.6.</b> Администратор может сначала потребовать удалить спорный контент. Если его приходится удалять администрации, участник может получить мут.

<b>3. Правила RP</b>
<b>3.1.</b> Уважайте соигроков и не мешайте остальным участникам.
<b>3.2.</b> Запрещены убийство персонажа и действия против воли соигрока без добровольного согласия.
<b>3.3.</b> Запрещены чрезмерно длинные RP-посты, которые мешают общему чату.

<b>4. Правила для администрации</b>
<b>4.1.</b> При муте или бане модератор/администратор обязан указать причину и срок действия наказания.

🦊 Кира использует <b>минимальную автоматическую модерацию</b>: она выдаёт предупреждения только за очевидные нарушения. Неоднозначные случаи остаются за администрацией и системой жалоб /report."""


class GroupRulesMiddleware(BaseMiddleware):
    SETTINGS_TTL = 300.0
    WARN_COOLDOWN = 180.0
    STICKER_WINDOW = 20.0
    MEDIA_WINDOW = 30.0

    def __init__(self) -> None:
        self._settings_cache: dict[int, tuple[float, bool]] = {}
        self._warned_at: dict[tuple[int, int, str], float] = {}
        self._stickers: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)
        self._media: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    async def invalidate(self, chat_id: int) -> None:
        self._settings_cache.pop(int(chat_id), None)

    async def _enabled(self, chat_id: int) -> bool:
        now = time.monotonic()
        cached = self._settings_cache.get(chat_id)
        if cached and now - cached[0] < self.SETTINGS_TTL:
            return cached[1]
        try:
            row = await GroupRulesSettingsManager.get(chat_id)
            enabled = bool(row.enabled)
        except Exception:
            log.exception("Failed to load group rules settings for %s", chat_id)
            enabled = True
        self._settings_cache[chat_id] = (now, enabled)
        return enabled

    @staticmethod
    async def _is_admin(message: Message) -> bool:
        user = message.from_user
        if not user:
            return False
        if is_owner(user.id):
            return True
        try:
            member = await message.bot.get_chat_member(message.chat.id, user.id)
            return member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}
        except Exception:
            return False

    @staticmethod
    def _forwarded_from_channel(message: Message) -> bool:
        origin = getattr(message, "forward_origin", None)
        if origin is None:
            return False
        name = origin.__class__.__name__.casefold()
        return "channel" in name or "chat" in name

    @staticmethod
    def _has_media(message: Message) -> bool:
        return bool(
            message.photo
            or message.video
            or message.animation
            or message.document
            or message.audio
            or message.voice
            or message.video_note
        )

    def _stateful_hit(self, message: Message) -> RuleHit | None:
        user = message.from_user
        if not user:
            return None
        now = time.monotonic()
        key = (message.chat.id, user.id)

        if message.sticker:
            q = self._stickers[key]
            while q and now - q[0][0] > self.STICKER_WINDOW:
                q.popleft()
            sticker_id = message.sticker.file_unique_id or message.sticker.file_id
            q.append((now, sticker_id))
            ids = [item[1] for item in q]
            if len(q) >= 5 or (len(q) >= 4 and len(set(ids[-4:])) < 4):
                q.clear()
                return RuleHit("1.5", "Стикер-флуд", "Слишком много стикеров подряд.", priority=90)

        is_file_media = bool(message.photo or message.video or message.animation or message.document or message.audio)
        if is_file_media and not message.media_group_id:
            q2 = self._media[key]
            while q2 and now - q2[0] > self.MEDIA_WINDOW:
                q2.popleft()
            q2.append(now)
            if len(q2) >= 5:
                q2.clear()
                return RuleHit("2.4", "Группировка файлов", "5+ файлов отправлены отдельно вместо альбома/группы.", priority=65)
        return None

    def _cooldown_ok(self, chat_id: int, user_id: int, rule_id: str) -> bool:
        now = time.monotonic()
        key = (chat_id, user_id, rule_id)
        last = self._warned_at.get(key, 0.0)
        if now - last < self.WARN_COOLDOWN:
            return False
        self._warned_at[key] = now
        return True

    @staticmethod
    async def _notify_staff(message: Message, hit: RuleHit, count: int) -> None:
        user = message.from_user
        if not user:
            return
        destinations: set[int] = set()
        try:
            chat = await ChatManager.get(message.chat.id)
            if chat and chat.admin_chat_id:
                destinations.add(int(chat.admin_chat_id))
        except Exception:
            pass
        if settings.owner_id:
            destinations.add(int(settings.owner_id))
        if not destinations:
            return
        text = (
            "🛡 <b>Kira: автоматическая модерация</b>\n"
            f"Чат: <code>{message.chat.id}</code>\n"
            f"Пользователь: <a href='tg://user?id={user.id}'>{html.escape(user.full_name)}</a> · <code>{user.id}</code>\n"
            f"Правило: <b>{html.escape(hit.rule_id)} · {html.escape(hit.title)}</b>\n"
            f"Причина: {html.escape(hit.reason)}\n"
            f"Предупреждений в этом чате: <b>{count}</b>\n"
            f"Сообщение: <code>{message.message_id}</code>"
        )
        for chat_id in destinations:
            try:
                await message.bot.send_message(chat_id, text)
            except Exception:
                continue

    async def _warn(self, message: Message, hit: RuleHit) -> None:
        user = message.from_user
        if not user or not self._cooldown_ok(message.chat.id, user.id, hit.rule_id):
            return
        try:
            await UserManager.get(user.id)
            count = await WarningManager.add(
                user.id,
                message.chat.id,
                f"Авто: правило {hit.rule_id} — {hit.title}. {hit.reason}",
            )
            await AuditLogManager.add(
                message.chat.id,
                0,
                "auto_rule_warn",
                f"rule={hit.rule_id}; {hit.reason}",
                user.id,
                int(time.time()),
            )
            await message.reply(
                "⚠️ <b>Предупреждение от Киры</b>\n"
                f"{html.escape(user.full_name)}, правило <b>{html.escape(hit.rule_id)}</b>: "
                f"{html.escape(hit.title)}.\n"
                f"{html.escape(hit.reason)}\n"
                f"Предупреждений в этом чате: <b>{count}</b>.\n"
                "Если считаешь срабатывание ошибочным, обратись к администрации."
            )
            if count >= 3:
                await self._notify_staff(message, hit, count)
        except Exception:
            log.exception("Automatic rules warning failed")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.chat.type == "private":
            return await handler(event, data)
        user = event.from_user
        if not user or user.is_bot:
            return await handler(event, data)
        text = (event.text or event.caption or "").strip()
        if text.startswith("/"):
            return await handler(event, data)
        if not await self._enabled(event.chat.id):
            return await handler(event, data)

        stateful = self._stateful_hit(event)
        hits = inspect_text(
            text,
            has_media=self._has_media(event),
            forwarded_from_channel=self._forwarded_from_channel(event),
        )
        if stateful:
            hits.insert(0, stateful)
        if not hits:
            return await handler(event, data)
        if await self._is_admin(event):
            return await handler(event, data)

        await self._warn(event, hits[0])
        return await handler(event, data)


group_rules_middleware = GroupRulesMiddleware()
