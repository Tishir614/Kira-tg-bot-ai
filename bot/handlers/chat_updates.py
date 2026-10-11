import os.path
import html
import time

from aiogram import F, Router
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import ChatMemberUpdated, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import log
from bot.bot import rp_manager
from bot.core import fetch_user
from bot.events import event_service
from bot.locale import _
from bot.moderation import moderation_service
from bot.pyrogram_core import PyroAPI
from bot.social import kira_social
from bot.sql import ChatManager, EconomyManager, NicknameManager, RelationshipManager, UserManager

router = Router()


async def _rp_display(user, chat_id: int) -> str:
    nickname = await NicknameManager.get(user.id, chat_id)
    if nickname:
        return f"<a href='tg://user?id={user.id}'>{html.escape(nickname)}</a>"
    return fetch_user(user)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def chat_handle(event: ChatMemberUpdated):
    chat_id = event.chat.id

    if event.chat.type != "supergroup":
        await event.answer(_("supergroup_only"))
        try:
            await event.bot.leave_chat(chat_id)
        except Exception as e:
            log.warning(f"Не удалось выйти из неподдерживаемого чата {chat_id}: {e}")
        return

    builder = InlineKeyboardBuilder()
    me = await event.bot.get_me()
    builder.button(text=_("open_private_btn"), url=f"https://t.me/{me.username}?start=help{abs(chat_id)}")

    chat = await ChatManager.get(chat_id)
    if not chat:
        await ChatManager.upsert(chat_id)
        await event.answer_photo(
            photo=FSInputFile(os.path.join("bot", "media", "banner.jpg")),
            caption=_("new_chat_message"),
            reply_markup=builder.as_markup()
        )
        try:
            await event.answer("🛡 В этой группе по умолчанию включён минимальный контроль правил. Полный список: /rules")
        except Exception:
            pass
    else:
        await event.answer_photo(
            photo=FSInputFile(os.path.join("bot", "media", "banner.jpg")),
            caption=_("exists_chat_message"),
            reply_markup=builder.as_markup()
        )


@router.message(F.text & ~F.private)
async def text_handler(message: Message):
    """Последний групповой обработчик: модерация, XP/отношения, дни рождения и RP."""
    if not message.from_user:
        return

    if await moderation_service.inspect(message):
        return

    try:
        await kira_social.observe(message)
    except Exception:
        log.exception("Kira social context observe failed")

    # Пассивная прогрессия. Бонус маленький, поэтому спамить ради XP невыгодно,
    # а антифлуд стоит перед начислением.
    try:
        _, level, leveled = await EconomyManager.add_xp(message.from_user.id, 3)
        if leveled:
            await message.reply(f"✨ Новый уровень: <b>{level}</b>! За повышение начислен бонус монет.")
    except Exception:
        log.exception("Не удалось начислить XP пользователю %s", message.from_user.id)

    try:
        user = await UserManager.get(message.from_user.id)
        if user and event_service.should_birthday_announce(
            message.chat.id,
            message.from_user.id,
            user.birthday_day,
            user.birthday_month,
        ):
            await message.reply(f"🎂 Сегодня день рождения у <b>{message.from_user.full_name}</b>! Поздравляем! 🎉")
    except Exception:
        log.exception("Birthday event failed")

    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot and reply.from_user.id != message.from_user.id:
        try:
            now = int(time.time())
            await RelationshipManager.bump(message.from_user.id, reply.from_user.id, friendship=1, now=now)
            await RelationshipManager.bump(reply.from_user.id, message.from_user.id, friendship=1, now=now)
        except Exception:
            log.exception("Relationship bump failed")

    trigger, argument = rp_manager.match(message.text, message.chat.id)
    if not trigger:
        await kira_social.maybe_reply(message)
        return

    user1 = await _rp_display(message.from_user, message.chat.id)

    # Reply имеет приоритет перед @username.
    if reply and reply.from_user:
        user2 = await _rp_display(reply.from_user, message.chat.id)
        await reply.reply(trigger.answer.format(u1=user1, u2=user2))
        return

    if "{u2}" not in trigger.answer:
        await message.reply(trigger.answer.format(u1=user1))
        return

    if not argument:
        await message.reply(_("no_username_provided"))
        return
    if not argument.startswith("@"):
        await message.reply(_("username_must_start_with_at"))
        return

    username = argument.split()[0]
    try:
        user_id = await PyroAPI.get_entity_id(username)
        if user_id is None:
            raise ValueError("Username not resolved")

        member = await message.bot.get_chat_member(message.chat.id, user_id)
        user2 = await _rp_display(member.user, message.chat.id)
        await message.reply(trigger.answer.format(u1=user1, u2=user2))
    except Exception as exc:
        log.warning("RP username lookup failed [%s, %s]: %s", message.chat.id, username, exc)
        await message.reply(_("error_get_user"))
