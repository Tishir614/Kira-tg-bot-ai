from __future__ import annotations

import html
import re
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.community_systems import (
    CommunityMarriageManager,
    GroupStaffManager,
    MATURE_RP_ACTIONS,
    MATURE_TRIGGER_TO_CODE,
    ROLE_LABELS,
    ROLE_RANK,
    MatureRPProposalManager,
    resolve_group_role,
)
from bot.pyrogram_core import PyroAPI
from bot.sql import AuditLogManager, ChatSettingsManager, UserManager

router = Router(name="community_life")


def _arg(message: Message) -> str:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def _resolve_target(message: Message, raw: str | None = None) -> tuple[int | None, str]:
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name
    token = (raw or _arg(message)).strip().split(maxsplit=1)[0] if (raw or _arg(message)).strip() else ""
    token = token.rstrip(",")
    if not token:
        return None, ""
    if token.lstrip("-").isdigit():
        user_id = int(token)
        try:
            member = await message.bot.get_chat_member(message.chat.id, user_id)
            return user_id, member.user.full_name
        except Exception:
            return user_id, f"ID {user_id}"
    if token.startswith("@"):
        try:
            user_id = await PyroAPI.get_entity_id(token)
            if user_id:
                try:
                    member = await message.bot.get_chat_member(message.chat.id, int(user_id))
                    return int(user_id), member.user.full_name
                except Exception:
                    return int(user_id), token
        except Exception:
            pass
    return None, ""


async def _display_name(bot, chat_id: int, user_id: int) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.user.full_name
    except Exception:
        return f"ID {user_id}"


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


# ---------------------------------------------------------------------------
# Community marriages
# ---------------------------------------------------------------------------

@router.message(Command("marry"))
@router.message(F.text.regexp(r"(?i)^брак(?:\s|$)"))
async def marry_group_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.reply("💍 Браки Киры работают внутри групповых бесед.")
        return
    target_id, target_name = await _resolve_target(message)
    if not target_id:
        await message.reply("💍 Ответь на сообщение пользователя командой <code>/marry</code> или укажи @username.")
        return
    if target_id == message.from_user.id:
        await message.reply("💍 Жениться на самом себе у Киры пока не получится 😼")
        return
    try:
        me = await message.bot.get_me()
        if target_id == me.id:
            await message.reply("🦊 Я польщена, но сама браки пользователей не заключаю с собой.")
            return
    except Exception:
        pass
    try:
        proposal = await CommunityMarriageManager.propose(message.chat.id, message.from_user.id, target_id)
    except ValueError as exc:
        await message.reply(f"💍 {html.escape(str(exc))}.")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="💍 Принять", callback_data=f"cmarry:a:{proposal.id}")
    builder.button(text="✖️ Отказать", callback_data=f"cmarry:d:{proposal.id}")
    builder.adjust(2)
    await message.reply(
        "💍 <b>Предложение руки и лапы</b>\n"
        f"{_mention(message.from_user.id, message.from_user.full_name)} делает предложение "
        f"{_mention(target_id, target_name)}.\n\n"
        "Решение принимает только тот, кому адресовано предложение. Оно действует 24 часа.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.regexp(r"^cmarry:[ad]:\d+$"))
async def marry_group_callback(call: CallbackQuery):
    _, action, raw_id = call.data.split(":")
    proposal_id = int(raw_id)
    proposal = await CommunityMarriageManager.get_proposal(proposal_id)
    if not proposal:
        await call.answer("Предложение не найдено.", show_alert=True)
        return
    if call.from_user.id != proposal.target_id:
        await call.answer("Это предложение адресовано не тебе.", show_alert=True)
        return
    try:
        if action == "d":
            await CommunityMarriageManager.decline(proposal_id, call.from_user.id)
            await call.message.edit_text("💔 Предложение отклонено.")
        else:
            marriage = await CommunityMarriageManager.accept(proposal_id, call.from_user.id)
            a_name = await _display_name(call.bot, marriage.chat_id, marriage.user_a_id)
            b_name = await _display_name(call.bot, marriage.chat_id, marriage.user_b_id)
            await call.message.edit_text(
                "💍 <b>В беседе новый брак!</b>\n"
                f"{_mention(marriage.user_a_id, a_name)} ❤️ {_mention(marriage.user_b_id, b_name)}\n"
                "Кира торжественно записала союз в свою лисью книгу браков."
            )
            await AuditLogManager.add(marriage.chat_id, call.from_user.id, "marriage", "accepted", marriage.user_a_id, int(time.time()))
    except (ValueError, PermissionError) as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer()


@router.message(Command("spouse"))
@router.message(F.text.regexp(r"(?i)^мой брак$"))
async def spouse_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return
    partner_id = await CommunityMarriageManager.partner_id(message.chat.id, message.from_user.id)
    if not partner_id:
        await message.reply("💍 В этой беседе ты пока не состоишь в браке.")
        return
    name = await _display_name(message.bot, message.chat.id, partner_id)
    await message.reply(f"💍 Твоя пара в этой беседе: {_mention(partner_id, name)} ❤️")


@router.message(Command("divorce"))
@router.message(F.text.regexp(r"(?i)^развод$"))
async def divorce_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return
    partner_id = await CommunityMarriageManager.divorce(message.chat.id, message.from_user.id)
    if not partner_id:
        await message.reply("💍 У тебя нет активного брака в этой беседе.")
        return
    name = await _display_name(message.bot, message.chat.id, partner_id)
    await AuditLogManager.add(message.chat.id, message.from_user.id, "divorce", "community marriage", partner_id, int(time.time()))
    await message.reply(f"💔 Брак с {_mention(partner_id, name)} расторгнут.")


@router.message(Command("marriages"))
async def marriages_cmd(message: Message):
    if message.chat.type == "private":
        return
    rows = await CommunityMarriageManager.list(message.chat.id, 20)
    if not rows:
        await message.reply("💍 В этой беседе пока нет зарегистрированных браков.")
        return
    lines = ["💍 <b>Браки беседы</b>"]
    for row in rows:
        a = await _display_name(message.bot, message.chat.id, row.user_a_id)
        b = await _display_name(message.bot, message.chat.id, row.user_b_id)
        lines.append(f"• {_mention(row.user_a_id, a)} ❤️ {_mention(row.user_b_id, b)}")
    await message.reply("\n".join(lines))


# ---------------------------------------------------------------------------
# Custom staff roles
# ---------------------------------------------------------------------------

ROLE_ALIASES = {
    "helper": "helper", "помощник": "helper", "хелпер": "helper",
    "moderator": "moderator", "mod": "moderator", "модер": "moderator", "модератор": "moderator",
    "admin": "admin", "админ": "admin", "administrator": "admin",
}


@router.message(Command("staff"))
@router.message(F.text.regexp(r"(?i)^состав(?:\s+админов)?$"))
async def staff_list_cmd(message: Message):
    if message.chat.type == "private":
        return
    rows = await GroupStaffManager.list(message.chat.id)
    lines = [
        "🛡 <b>Команда беседы</b>",
        "Telegram-владелец и Telegram-администраторы сохраняют свои системные права.",
    ]
    if not rows:
        lines.append("\nДополнительные роли Киры пока не назначены.")
    else:
        for row in rows:
            name = await _display_name(message.bot, message.chat.id, row.user_id)
            lines.append(f"• <b>{ROLE_LABELS.get(row.role, row.role)}</b> — {_mention(row.user_id, name)}")
    lines += [
        "\n<b>Полномочия:</b>",
        "🧩 Помощник: предупреждения, просмотр жалоб.",
        "🛡 Модератор: + снятие варнов, мут/размут, кик, обработка жалоб, modlog.",
        "👑 Администратор: + бан/разбан, настройки правил/Киры, назначение помощников и модераторов.",
        "⭐ Владелец: полный доступ, включая назначение администраторов.",
    ]
    await message.reply("\n".join(lines))


@router.message(Command("role"))
async def role_set_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return
    actor_role = await resolve_group_role(message.bot, message.chat.id, message.from_user.id, owner_id=settings.owner_id)
    if ROLE_RANK.get(actor_role, 0) < ROLE_RANK["admin"]:
        await message.reply("🛡 Назначать роли могут администраторы беседы.")
        return
    raw = _arg(message)
    if not raw:
        await message.reply("Использование: ответь на сообщение <code>/role helper|moderator|admin</code> или <code>/role moderator @user</code>.")
        return
    parts = raw.split()
    role = ROLE_ALIASES.get(parts[0].casefold())
    if not role:
        await message.reply("Роли: <code>helper</code>, <code>moderator</code>, <code>admin</code>.")
        return
    if role == "admin" and actor_role != "owner":
        await message.reply("👑 Назначать роль администратора может только владелец беседы или главный владелец Kira.")
        return
    target_raw = parts[1] if len(parts) > 1 else ""
    target_id, target_name = await _resolve_target(message, target_raw)
    if not target_id:
        await message.reply("Ответь этой командой на сообщение пользователя или укажи @username.")
        return
    if target_id == message.from_user.id and actor_role != "owner":
        await message.reply("Нельзя повышать самого себя через Kira.")
        return
    target_role = await resolve_group_role(message.bot, message.chat.id, target_id, owner_id=settings.owner_id)
    if target_role == "owner":
        await message.reply("👑 Роль владельца задаётся самим Telegram и не меняется этой командой.")
        return
    row = await GroupStaffManager.set(message.chat.id, target_id, role, message.from_user.id)
    await AuditLogManager.add(message.chat.id, message.from_user.id, "staff_role", role, target_id, int(time.time()))
    await message.reply(f"🛡 {_mention(target_id, target_name)} теперь <b>{ROLE_LABELS[row.role]}</b> этой беседы.")


@router.message(Command("unrole"))
async def role_remove_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return
    actor_role = await resolve_group_role(message.bot, message.chat.id, message.from_user.id, owner_id=settings.owner_id)
    if ROLE_RANK.get(actor_role, 0) < ROLE_RANK["admin"]:
        await message.reply("🛡 Снимать роли могут администраторы беседы.")
        return
    target_id, target_name = await _resolve_target(message)
    if not target_id:
        await message.reply("Ответь на сообщение пользователя командой <code>/unrole</code> или укажи @username.")
        return
    row = await GroupStaffManager.get(message.chat.id, target_id)
    if row and row.role == "admin" and actor_role != "owner":
        await message.reply("👑 Снять роль администратора может только владелец.")
        return
    removed = await GroupStaffManager.remove(message.chat.id, target_id)
    if removed:
        await AuditLogManager.add(message.chat.id, message.from_user.id, "staff_unrole", "", target_id, int(time.time()))
        await message.reply(f"✅ Дополнительная роль Киры снята с {_mention(target_id, target_name)}.")
    else:
        await message.reply("У пользователя нет дополнительной роли Киры.")


# ---------------------------------------------------------------------------
# Consent-gated adult RP shortcuts
# ---------------------------------------------------------------------------

_MATURE_PATTERN = re.compile(
    r"(?i)^(?:секс|переспать|трахнуть|интим|отсосать|ночь вместе|провести ночь|страстно поцеловать|горячий поцелуй|в кровать|обниматься в кровати|соблазнить|флирт 18\+)(?:\s|$)"
)


def _find_mature_trigger(text: str) -> tuple[str | None, str]:
    lowered = text.casefold().strip()
    for trigger in sorted(MATURE_TRIGGER_TO_CODE, key=len, reverse=True):
        if lowered == trigger or lowered.startswith(trigger + " "):
            return trigger, text.strip()[len(trigger):].strip()
    return None, ""


@router.message(Command("rp18_actions"))
async def rp18_actions_cmd(message: Message):
    lines = [
        "🔞 <b>Парные RP18-действия</b>",
        "Работают только после подтверждения 18+ у обоих пользователей, при включённом Mature Mode и после отдельного согласия второго участника.",
        "",
    ]
    for data in MATURE_RP_ACTIONS.values():
        lines.append("• " + " / ".join(f"<code>{html.escape(x)}</code>" for x in sorted(data["triggers"])))
    lines.append("\nПример: ответь на сообщение словом <code>секс</code> или напиши <code>секс @username</code>.")
    await message.reply("\n".join(lines))


@router.message(F.text.regexp(_MATURE_PATTERN))
async def mature_pair_action_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.reply("🔞 Парные RP-действия предназначены для групповых бесед.")
        return
    trigger, rest = _find_mature_trigger(message.text or "")
    if not trigger:
        return
    action_code = MATURE_TRIGGER_TO_CODE[trigger]
    chat_settings = await ChatSettingsManager.get(message.chat.id)
    if not chat_settings.mature_mode:
        await message.reply("🔞 Mature Mode в этой группе выключен. Администратор может включить его через <code>/mature on</code>.")
        return
    if not await UserManager.is_adult_confirmed(message.from_user.id):
        await message.reply("🔞 Сначала подтверди 18+ командой <code>/mature accept</code>.")
        return
    target_id, target_name = await _resolve_target(message, rest)
    if not target_id:
        await message.reply(f"🔞 Ответь действием <code>{html.escape(trigger)}</code> на сообщение взрослого участника или укажи @username.")
        return
    if target_id == message.from_user.id:
        await message.reply("Для парного действия нужен другой участник.")
        return
    if not await UserManager.is_adult_confirmed(target_id):
        await message.reply("🔞 Второй участник ещё не подтвердил 18+ через <code>/mature accept</code>.")
        return
    try:
        proposal = await MatureRPProposalManager.create(message.chat.id, message.from_user.id, target_id, action_code)
    except ValueError as exc:
        await message.reply(html.escape(str(exc)))
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Согласен(на)", callback_data=f"mrp:a:{proposal.id}")
    builder.button(text="✖️ Нет", callback_data=f"mrp:d:{proposal.id}")
    builder.adjust(2)
    await message.reply(
        "🔞 <b>Запрос на взрослое RP-действие</b>\n"
        f"{_mention(message.from_user.id, message.from_user.full_name)} → {_mention(target_id, target_name)}\n"
        f"Действие: <code>{html.escape(trigger)}</code>\n\n"
        "Кира выполнит его только после явного согласия второго участника. Запрос действует 10 минут.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.regexp(r"^mrp:[ad]:\d+$"))
async def mature_pair_action_callback(call: CallbackQuery):
    _, action, raw_id = call.data.split(":")
    proposal = await MatureRPProposalManager.get(int(raw_id))
    if not proposal:
        await call.answer("Запрос не найден.", show_alert=True)
        return
    if proposal.target_id != call.from_user.id:
        await call.answer("Этот запрос адресован другому пользователю.", show_alert=True)
        return
    try:
        row = await MatureRPProposalManager.decide(proposal.id, call.from_user.id, accept=action == "a")
    except (ValueError, PermissionError) as exc:
        await call.answer(str(exc), show_alert=True)
        return
    if action == "d":
        await call.message.edit_text("🔞 RP18-действие отклонено. Никаких последствий.")
        await call.answer()
        return
    settings_row = await ChatSettingsManager.get(row.chat_id)
    if not settings_row.mature_mode or not await UserManager.is_adult_confirmed(row.initiator_id) or not await UserManager.is_adult_confirmed(row.target_id):
        await call.message.edit_text("🔞 Действие отменено: Mature Mode или подтверждение 18+ изменились.")
        await call.answer()
        return
    data = MATURE_RP_ACTIONS.get(row.action_code)
    if not data:
        await call.answer("Действие больше недоступно.", show_alert=True)
        return
    u1 = await _display_name(call.bot, row.chat_id, row.initiator_id)
    u2 = await _display_name(call.bot, row.chat_id, row.target_id)
    text = data["text"].format(u1=_mention(row.initiator_id, u1), u2=_mention(row.target_id, u2))
    await call.message.edit_text(text)
    await AuditLogManager.add(row.chat_id, row.target_id, "mature_rp_consent", row.action_code, row.initiator_id, int(time.time()))
    await call.answer("Согласие принято")
