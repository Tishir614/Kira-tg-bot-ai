from __future__ import annotations

import html
import random
import re
import time
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

from bot import log
from bot.config import settings
from bot.owners import is_owner
from bot.community_systems import ROLE_RANK, resolve_group_role, role_has_permission
from bot.group_features import (
    GroupActivityManager,
    GroupAuditManager,
    GroupConversationSettingsManager,
    GroupReportManager,
    GroupRulesSettingsManager,
    WarningManager,
    activity_progress,
    format_activity_name,
)
from bot.pyrogram_core import PyroAPI
from bot.recovery import recovery_runtime
from bot.group_rules import RULES_TEXT, group_rules_middleware
from bot.sql import AuditLogManager, ChatManager, UserManager


router = Router(name="community")


def _arg(message: Message) -> str:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def _actor_role(message: Message) -> str:
    if not message.from_user or message.chat.type == "private":
        return "member"
    return await resolve_group_role(
        message.bot, message.chat.id, message.from_user.id, owner_id=settings.owner_id
    )


async def _is_admin(message: Message) -> bool:
    return ROLE_RANK.get(await _actor_role(message), 0) >= ROLE_RANK["admin"]


async def _require_permission(message: Message, permission: str, label: str) -> bool:
    if message.chat.type == "private":
        await message.reply("Эта команда работает в группе.")
        return False
    role = await _actor_role(message)
    if not role_has_permission(role, permission):
        await message.reply(f"🛡 Для этой команды нужна роль с полномочием: <b>{html.escape(label)}</b>.")
        return False
    return True


async def _require_admin(message: Message) -> bool:
    return await _require_permission(message, "settings", "администратор")


async def _target(message: Message, *, allow_arg: bool = True) -> tuple[int | None, str]:
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name
    if not allow_arg:
        return None, ""
    raw = _arg(message).split(maxsplit=1)[0] if _arg(message) else ""
    raw = raw.rstrip(",")
    if raw.lstrip("-").isdigit():
        return int(raw), f"ID {raw}"
    if raw.startswith("@"):
        try:
            user_id = await PyroAPI.get_entity_id(raw)
            if user_id:
                return int(user_id), raw
        except Exception:
            pass
    return None, ""


async def _protect_target(message: Message, user_id: int) -> bool:
    if is_owner(user_id):
        await message.reply("🦊 Хозяина я не трогаю.")
        return False
    try:
        me = await message.bot.get_me()
        if user_id == me.id:
            await message.reply("Я сама себя модерировать не буду 😼")
            return False
        member = await message.bot.get_chat_member(message.chat.id, user_id)
        if member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
            await message.reply("🛡 Нельзя применить это действие к администратору группы.")
            return False
    except Exception:
        # Telegram may not return a member for already-left/banned users; unban still needs to work.
        pass

    if message.from_user:
        actor_role = await _actor_role(message)
        target_role = await resolve_group_role(
            message.bot, message.chat.id, user_id, owner_id=settings.owner_id
        )
        if actor_role != "owner" and target_role != "member" and ROLE_RANK.get(target_role, 0) >= ROLE_RANK.get(actor_role, 0):
            await message.reply("🛡 Нельзя модерировать участника с равной или более высокой ролью Киры.")
            return False
    return True


def _duration(raw: str, default_minutes: int = 10) -> tuple[int, str]:
    token = (raw.split(maxsplit=1)[0] if raw else "").casefold()
    m = re.fullmatch(r"(\d+)([mмhчdд]?)", token)
    if not m:
        return default_minutes, raw
    value = max(1, int(m.group(1)))
    unit = m.group(2)
    factor = 1
    if unit in {"h", "ч"}:
        factor = 60
    elif unit in {"d", "д"}:
        factor = 1440
    minutes = max(1, min(value * factor, 43200))
    rest = raw[len(m.group(0)):].strip()
    return minutes, rest


@router.message(Command("activity"))
@router.message(F.text.regexp(r"(?i)^(?:активность|топ активность)(?:\s|$)"))
async def activity_cmd(message: Message):
    if message.chat.type == "private":
        await message.reply("📊 Таблица активности доступна внутри группы.")
        return
    raw = _arg(message)
    limit = int(raw) if raw.isdigit() else 10
    limit = max(3, min(limit, 20))
    rows = await GroupActivityManager.top(message.chat.id, limit)
    totals = await GroupActivityManager.totals(message.chat.id)
    if not rows:
        await message.reply("📊 Пока недостаточно данных об активности.")
        return
    lines = [
        "📊 <b>Активность группы</b>",
        f"Участников в таблице: <b>{totals['users']}</b> · сообщений учтено: <b>{totals['messages']}</b>",
        "",
        "<b># · уровень · сообщения · пользователь</b>",
    ]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for idx, row in enumerate(rows, start=1):
        rank = medals.get(idx, f"{idx}.")
        lines.append(
            f"{rank} <b>Lv.{row.activity_level}</b> · {row.message_count} msg · {format_activity_name(row)}"
        )
    lines.append("\nУровень активности считается отдельно для каждой группы и растёт от сообщений.")
    await message.reply("\n".join(lines))


@router.message(Command("myactivity"))
@router.message(F.text.regexp(r"(?i)^моя активность$"))
async def my_activity_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.reply("Эта статистика считается отдельно в каждой группе.")
        return
    row = await GroupActivityManager.get(message.chat.id, message.from_user.id)
    if not row:
        await message.reply("Ты ещё не попал в таблицу активности.")
        return
    level, inside, needed = activity_progress(row.activity_xp)
    pct = int(inside * 100 / max(1, needed))
    blocks = max(0, min(10, pct // 10))
    bar = "█" * blocks + "░" * (10 - blocks)
    await message.reply(
        "🦊 <b>Твоя активность</b>\n"
        f"Уровень: <b>{level}</b>\n"
        f"Сообщений: <b>{row.message_count}</b>\n"
        f"Текстовых: {row.text_messages} · медиа: {row.media_messages} · голосовых: {row.voice_messages}\n"
        f"XP активности: {inside}/{needed}\n<code>{bar}</code> {pct}%"
    )


@router.message(Command("groupstats"))
async def group_stats_cmd(message: Message):
    if message.chat.type == "private":
        return
    totals = await GroupActivityManager.totals(message.chat.id)
    prefs = await GroupConversationSettingsManager.get(message.chat.id)
    await message.reply(
        "📈 <b>Статистика группы</b>\n"
        f"Участников с активностью: <b>{totals['users']}</b>\n"
        f"Учтённых сообщений: <b>{totals['messages']}</b>\n"
        f"Живое общение Киры: <b>{'включено' if prefs.enabled else 'выключено'}</b>\n"
        f"Шанс спонтанного ответа: <b>{prefs.spontaneous_chance}%</b>\n"
        f"Кулдаун: <b>{max(1, prefs.cooldown_seconds // 60)} мин.</b>"
    )


CHAT_TOPICS = [
    "Какой навык вы бы мгновенно прокачали до максимума и почему?",
    "Если бы эта беседа была игрой, кто был бы каким классом?",
    "Назовите один фильм, игру или трек, который вы готовы защищать до последнего.",
    "Какой самый странный, но полезный совет вам когда-либо давали?",
    "Представьте: у беседы появился общий дом. Какую комнату каждый занял бы первой?",
    "Какой маленький апгрейд сделал бы вашу неделю заметно лучше?",
    "Кто в этой беседе пережил бы хоррор-фильм дольше всех и почему?",
    "Вы получили 24 часа без обязанностей. На что их потратите?",
]

CHAT_CHALLENGES = [
    "каждый кидает по одному треку, который описывает его настроение",
    "за 10 минут придумайте беседе новое абсурдное название",
    "каждый пишет один факт о себе, который остальные вряд ли угадают",
    "выберите мем дня и объясните, почему именно он",
    "соберите мини-тирлист любимых игр или сериалов прямо в чате",
]


def _activity_link(row) -> str:
    name = html.escape(row.display_name or str(row.user_id))
    return f"<a href='tg://user?id={row.user_id}'>{name}</a>"


@router.message(Command("who"))
@router.message(F.text.regexp(r"(?i)^кто сегодня(?:\s|$)"))
async def who_cmd(message: Message):
    if message.chat.type == "private":
        await message.reply("🎲 Эта штука работает только в беседе.")
        return
    rows = await GroupActivityManager.top(message.chat.id, 40)
    rows = [row for row in rows if row.user_id != getattr(message.bot, "id", None)]
    if not rows:
        await message.reply("Пока слишком мало активности, чтобы выбирать участника.")
        return
    chosen = random.choice(rows[: min(20, len(rows))])
    role = _arg(message)
    if message.text and message.text.casefold().startswith("кто сегодня"):
        role = message.text[len("кто сегодня"):].strip()
    label = html.escape(role[:120]) if role else random.choice([
        "главный герой дня", "ночной философ", "магистр мемов", "самый вероятный спаситель чата", "хранитель хаоса"
    ])
    await message.reply(f"🎲 Сегодня <b>{label}</b> — {_activity_link(chosen)}.")


@router.message(Command("pair"))
@router.message(F.text.lower().in_({"дуэт дня", "пара для игры"}))
async def pair_cmd(message: Message):
    if message.chat.type == "private":
        await message.reply("👥 Дуэт выбирается из активных участников беседы.")
        return
    rows = await GroupActivityManager.top(message.chat.id, 40)
    if len(rows) < 2:
        await message.reply("Нужно хотя бы два активных участника.")
        return
    a, b = random.sample(rows[: min(20, len(rows))], 2)
    missions = [
        "собрать идеальный плейлист из 5 треков",
        "придумать самый нелепый сюжет для игры",
        "защитить противоположные мнения в мини-дебатах",
        "выбрать мем, который лучше всего описывает беседу",
        "придумать название для вымышленной группы или сервера",
    ]
    await message.reply(
        f"👥 <b>Дуэт беседы</b>\n{_activity_link(a)} + {_activity_link(b)}\n"
        f"🎯 Мини-миссия: {random.choice(missions)}."
    )


@router.message(Command("topic"))
@router.message(F.text.lower().in_({"тема для беседы", "оживи чат"}))
async def topic_cmd(message: Message):
    if message.chat.type == "private":
        await message.reply("💬 Эту команду лучше использовать в группе.")
        return
    if random.random() < 0.28:
        await message.reply(f"🎯 <b>Мини-задание беседы:</b> {random.choice(CHAT_CHALLENGES)}.")
    else:
        await message.reply(f"💬 <b>Тема беседы:</b> {random.choice(CHAT_TOPICS)}")


@router.message(Command("chatmood"))
@router.message(F.text.lower().in_({"настроение беседы", "пульс беседы"}))
async def chatmood_cmd(message: Message):
    if message.chat.type == "private":
        await message.reply("🌡 Пульс считается внутри группы.")
        return
    totals = await GroupActivityManager.totals(message.chat.id)
    rows = await GroupActivityManager.top(message.chat.id, 5)
    messages = totals["messages"]
    users = totals["users"]
    if messages >= 5000:
        mood = "🔥 чат кипит, клавиатуры просят отпуск"
    elif messages >= 1000:
        mood = "⚡ бодрая и живая беседа"
    elif messages >= 200:
        mood = "🌿 спокойный, но устойчивый движ"
    else:
        mood = "🌙 камерная атмосфера, есть куда разогнаться"
    top = _activity_link(rows[0]) if rows else "пока никто"
    await message.reply(
        "🌡 <b>Пульс беседы</b>\n"
        f"Состояние: <b>{mood}</b>\n"
        f"Участников в статистике: <b>{users}</b>\n"
        f"Учтено сообщений: <b>{messages}</b>\n"
        f"Лидер активности: {top}\n\n"
        "Разогреть чат: <code>/topic</code> · <code>/who</code> · <code>/pair</code>"
    )


@router.message(Command("kira_chat"))
@router.message(F.text.regexp(r"(?i)^кира\s+общение(?:\s|$)"))
async def kira_chat_cmd(message: Message):
    if not await _require_admin(message):
        return
    raw = _arg(message).casefold()
    if message.text and message.text.casefold().startswith("кира общение"):
        raw = message.text[len("кира общение"):].strip().casefold()
    if raw in {"вкл", "on", "1", "да"}:
        prefs = await GroupConversationSettingsManager.update(message.chat.id, enabled=True)
    elif raw in {"выкл", "off", "0", "нет"}:
        prefs = await GroupConversationSettingsManager.update(message.chat.id, enabled=False)
    else:
        prefs = await GroupConversationSettingsManager.get(message.chat.id)
        await message.reply(
            f"🦊 Живое общение сейчас <b>{'включено' if prefs.enabled else 'выключено'}</b>.\n"
            "Использование: <code>/kira_chat on</code> или <code>/kira_chat off</code>."
        )
        return
    await message.reply(f"🦊 Живое общение Киры {'включено' if prefs.enabled else 'выключено'}.")


@router.message(Command("kira_chance"))
async def kira_chance_cmd(message: Message):
    if not await _require_admin(message):
        return
    raw = _arg(message)
    if not raw.isdigit():
        prefs = await GroupConversationSettingsManager.get(message.chat.id)
        await message.reply(f"Текущий шанс: <b>{prefs.spontaneous_chance}%</b>. Диапазон 0–25%.")
        return
    prefs = await GroupConversationSettingsManager.update(
        message.chat.id, spontaneous_chance=max(0, min(25, int(raw)))
    )
    await message.reply(f"🦊 Шанс спонтанного вступления Киры в разговор: <b>{prefs.spontaneous_chance}%</b>.")


def _rule_chunks(text: str, limit: int = 3600) -> list[str]:
    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = paragraph
    if current:
        parts.append(current)
    return parts


@router.message(Command("rules"))
@router.message(F.text.regexp(r"(?i)^правила(?:\s|$)"))
async def rules_cmd(message: Message):
    raw = _arg(message).casefold()
    if message.text and not message.text.startswith("/"):
        raw = message.text[len("правила"):].strip().casefold()

    if raw in {"on", "вкл", "включить", "off", "выкл", "выключить"}:
        if not await _require_admin(message):
            return
        enabled = raw in {"on", "вкл", "включить"}
        await GroupRulesSettingsManager.set_enabled(message.chat.id, enabled)
        await group_rules_middleware.invalidate(message.chat.id)
        await message.reply(
            "🛡 Минимальная автоматическая модерация правил "
            + ("<b>включена</b>." if enabled else "<b>выключена</b>.")
        )
        return

    if raw in {"status", "статус"}:
        row = await GroupRulesSettingsManager.get(message.chat.id)
        await message.reply(
            "🛡 Контроль правил: "
            + ("<b>включён</b>." if row.enabled else "<b>выключен</b>.")
            + "\nРежим: <b>минимальный</b> — только очевидные нарушения получают авто-предупреждение."
        )
        return

    for idx, chunk in enumerate(_rule_chunks(RULES_TEXT)):
        if idx == 0:
            await message.reply(chunk)
        else:
            await message.answer(chunk)


@router.message(Command("warn"))
@router.message(F.text.regexp(r"(?i)^варн(?:\s|$)"))
async def warn_cmd(message: Message):
    if not await _require_permission(message, "warn", "помощник или выше"):
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        await message.reply("Ответь на сообщение пользователя: <code>/warn причина</code>.")
        return
    if not await _protect_target(message, target_id):
        return
    await UserManager.get(target_id)
    reason = _arg(message)
    if message.text and message.text.casefold().startswith("варн"):
        reason = message.text[4:].strip()
    if not reason:
        await message.reply("По правилам администрации нужно указать причину: <code>/warn причина</code>.")
        return
    count = await WarningManager.add(target_id, message.chat.id, reason)
    await AuditLogManager.add(message.chat.id, message.from_user.id, "warn", reason, target_id, int(time.time()))
    text = f"⚠️ <b>{html.escape(target_name)}</b> получает предупреждение. Всего: <b>{count}</b>.\nПричина: {html.escape(reason[:800])}"
    if count >= 3:
        try:
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            await message.bot.restrict_chat_member(
                message.chat.id,
                target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            text += "\n🔇 За 3+ предупреждения автоматически выдан мут на 1 час."
            await AuditLogManager.add(message.chat.id, 0, "auto_warn_mute", "60m", target_id, int(time.time()))
        except Exception as exc:
            log.warning("warn escalation mute failed: %s", exc)
    await message.reply(text)


@router.message(Command("unwarn"))
async def unwarn_cmd(message: Message):
    if not await _require_permission(message, "unwarn", "модератор или выше"):
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        await message.reply("Ответь на сообщение пользователя командой <code>/unwarn</code>.")
        return
    removed = await WarningManager.remove_latest(target_id, message.chat.id)
    count = await WarningManager.count(target_id, message.chat.id)
    await message.reply(
        f"✅ Последнее предупреждение снято с {html.escape(target_name)}. Осталось: <b>{count}</b>."
        if removed else "У пользователя нет предупреждений в этой группе."
    )


@router.message(Command("warnings"))
async def warnings_cmd(message: Message):
    if message.chat.type == "private":
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        if not message.from_user:
            return
        target_id, target_name = message.from_user.id, message.from_user.full_name
    rows = await WarningManager.latest(target_id, message.chat.id, 10)
    if not rows:
        await message.reply(f"✅ У {html.escape(target_name)} нет предупреждений.")
        return
    lines = [f"⚠️ <b>Предупреждения: {html.escape(target_name)}</b>"]
    for idx, row in enumerate(reversed(rows), start=1):
        date = datetime.fromtimestamp(row.created_at, tz=timezone.utc).strftime("%d.%m %H:%M")
        lines.append(f"{idx}. {html.escape(row.cause[:300])} <i>({date} UTC)</i>")
    await message.reply("\n".join(lines))


@router.message(Command("ban"))
async def ban_cmd(message: Message):
    if not await _require_permission(message, "ban", "администратор"):
        return
    target_id, target_name = await _target(message)
    if not target_id:
        await message.reply("Ответь на сообщение или используй <code>/ban USER_ID причина</code>.")
        return
    if not await _protect_target(message, target_id):
        return
    reason = _arg(message)
    if not message.reply_to_message and reason:
        reason = reason.split(maxsplit=1)[1] if len(reason.split(maxsplit=1)) == 2 else ""
    if not reason:
        await message.reply("По правилу 4.1 укажи причину бана. Пример: <code>/ban USER_ID реклама</code>.")
        return
    try:
        await message.bot.ban_chat_member(message.chat.id, target_id)
        await AuditLogManager.add(message.chat.id, message.from_user.id, "ban", reason, target_id, int(time.time()))
        await message.reply(f"⛔ <b>{html.escape(target_name)}</b> забанен.\nСрок: <b>бессрочно</b>\nПричина: {html.escape(reason[:800])}")
    except Exception as exc:
        await message.reply(f"Не удалось забанить: {html.escape(str(exc)[:800])}")


@router.message(Command("unban"))
async def unban_cmd(message: Message):
    if not await _require_permission(message, "ban", "администратор"):
        return
    target_id, target_name = await _target(message)
    if not target_id:
        await message.reply("Используй <code>/unban USER_ID</code>.")
        return
    try:
        await message.bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        await AuditLogManager.add(message.chat.id, message.from_user.id, "unban", "", target_id, int(time.time()))
        await message.reply(f"✅ {html.escape(target_name)} разбанен.")
    except Exception as exc:
        await message.reply(f"Не удалось разбанить: {html.escape(str(exc)[:800])}")


@router.message(Command("kick"))
async def kick_cmd(message: Message):
    if not await _require_permission(message, "kick", "модератор или выше"):
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        await message.reply("Ответь командой <code>/kick причина</code> на сообщение пользователя.")
        return
    if not await _protect_target(message, target_id):
        return
    reason = _arg(message)
    if not reason:
        await message.reply("По правилу 4.1 укажи причину исключения: <code>/kick причина</code>.")
        return
    try:
        await message.bot.ban_chat_member(message.chat.id, target_id)
        await message.bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        await AuditLogManager.add(message.chat.id, message.from_user.id, "kick", reason, target_id, int(time.time()))
        await message.reply(f"👢 {html.escape(target_name)} исключён из группы.\nПричина: {html.escape(reason[:800])}")
    except Exception as exc:
        await message.reply(f"Не удалось исключить: {html.escape(str(exc)[:800])}")


@router.message(Command("mute"))
async def mute_cmd(message: Message):
    if not await _require_permission(message, "mute", "модератор или выше"):
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        await message.reply("Ответь на сообщение: <code>/mute 10m причина</code>. Поддерживаются m/h/d.")
        return
    if not await _protect_target(message, target_id):
        return
    minutes, reason = _duration(_arg(message), 10)
    if not reason:
        await message.reply("По правилу 4.1 укажи срок и причину: <code>/mute 10m причина</code>.")
        return
    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await message.bot.restrict_chat_member(
            message.chat.id,
            target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await AuditLogManager.add(message.chat.id, message.from_user.id, "mute", f"{minutes}m; {reason}", target_id, int(time.time()))
        await message.reply(f"🔇 {html.escape(target_name)} получает мут на <b>{minutes} мин.</b>\nПричина: {html.escape(reason[:800])}")
    except Exception as exc:
        await message.reply(f"Не удалось выдать мут: {html.escape(str(exc)[:800])}")


@router.message(Command("unmute"))
async def unmute_cmd(message: Message):
    if not await _require_permission(message, "mute", "модератор или выше"):
        return
    target_id, target_name = await _target(message, allow_arg=False)
    if not target_id:
        await message.reply("Ответь командой <code>/unmute</code> на пользователя.")
        return
    try:
        await message.bot.restrict_chat_member(
            message.chat.id,
            target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_invite_users=True,
            ),
        )
        await AuditLogManager.add(message.chat.id, message.from_user.id, "unmute", "", target_id, int(time.time()))
        await message.reply(f"🔊 Мут снят с {html.escape(target_name)}.")
    except Exception as exc:
        await message.reply(f"Не удалось снять мут: {html.escape(str(exc)[:800])}")


def _report_text(row, *, detailed: bool = False) -> str:
    status_icon = {"open": "🟠", "resolved": "✅", "rejected": "⚪"}.get(row.status, "•")
    lines = [
        f"{status_icon} <b>Жалоба #{row.id}</b> · <code>{html.escape(row.status)}</code>",
        f"На: <a href='tg://user?id={row.target_id}'>{html.escape(row.target_name or str(row.target_id))}</a> · <code>{row.target_id}</code>",
        f"От: <code>{row.reporter_id}</code>",
        f"Причина: {html.escape((row.reason or 'Без причины')[:700])}",
    ]
    if row.message_id:
        lines.append(f"Сообщение: <code>{row.message_id}</code>")
    if detailed and row.message_text:
        lines.append(f"Фрагмент: <blockquote>{html.escape(row.message_text[:900])}</blockquote>")
    if detailed and row.resolution:
        lines.append(f"Решение: {html.escape(row.resolution[:700])}")
    return "\n".join(lines)


async def _notify_report_staff(message: Message, row) -> None:
    text = "🚨 <b>Новая жалоба в группе</b>\n" + _report_text(row, detailed=True)
    destinations: set[int] = set()
    try:
        chat = await ChatManager.get(message.chat.id)
        if chat and chat.admin_chat_id:
            destinations.add(int(chat.admin_chat_id))
    except Exception:
        pass
    if settings.owner_id:
        destinations.add(int(settings.owner_id))

    # If no dedicated admin chat is configured, try private notifications to admins.
    if not destinations:
        try:
            admins = await message.bot.get_chat_administrators(message.chat.id)
            for member in admins[:8]:
                if not member.user.is_bot:
                    destinations.add(int(member.user.id))
        except Exception:
            pass

    for chat_id in destinations:
        try:
            await message.bot.send_message(chat_id, text)
        except Exception:
            # Telegram may forbid DMs to admins who never opened the bot. /reports remains canonical.
            continue


@router.message(Command("report"))
@router.message(F.text.regexp(r"(?i)^жалоба(?:\s|$)"))
async def report_cmd(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.reply("🚨 Жалобу нужно отправлять в группе ответом на сообщение пользователя.")
        return
    target_message = message.reply_to_message
    if not target_message or not target_message.from_user:
        await message.reply("Ответь на проблемное сообщение командой <code>/report причина</code> или <code>жалоба причина</code>.")
        return
    target = target_message.from_user
    if target.id == message.from_user.id:
        await message.reply("На своё сообщение жалобу отправить нельзя.")
        return
    reason = _arg(message) or "Причина не указана"
    evidence = (target_message.text or target_message.caption or "[медиа/стикер/голосовое сообщение]").strip()
    try:
        row, created = await GroupReportManager.create(
            chat_id=message.chat.id,
            reporter_id=message.from_user.id,
            target_id=target.id,
            target_name=target.full_name or target.username or str(target.id),
            message_id=target_message.message_id,
            message_text=evidence,
            reason=reason,
        )
    except ValueError as exc:
        await message.reply(f"🚨 {html.escape(str(exc))}")
        return
    if not created:
        await message.reply(f"🚨 Эта жалоба уже зарегистрирована как <b>#{row.id}</b>.")
        return

    await AuditLogManager.add(message.chat.id, message.from_user.id, "report", reason[:500], target.id, int(time.time()))
    await _notify_report_staff(message, row)

    # Hide the reporter command from the public chat where possible.
    deleted = False
    try:
        await message.delete()
        deleted = True
    except Exception:
        pass
    confirmation = f"🚨 Жалоба <b>#{row.id}</b> принята и передана администрации. Не дублируй её повторно."
    try:
        await message.bot.send_message(message.from_user.id, confirmation)
    except Exception:
        if not deleted:
            await message.reply(confirmation)


@router.message(Command("reports"))
async def reports_cmd(message: Message):
    if not await _require_permission(message, "reports_view", "помощник или выше"):
        return
    mode = (_arg(message) or "open").casefold()
    status = None if mode in {"all", "все"} else "open"
    rows = await GroupReportManager.recent(message.chat.id, status=status, limit=15)
    stats = await GroupReportManager.stats(message.chat.id)
    if not rows:
        await message.reply(
            f"🚨 Жалоб нет. Открытых: <b>{stats['open']}</b> · решено: {stats['resolved']} · отклонено: {stats['rejected']}"
        )
        return
    lines = [
        "🚨 <b>Жалобы группы</b>",
        f"Открытых: <b>{stats['open']}</b> · решено: {stats['resolved']} · отклонено: {stats['rejected']}",
        "",
    ]
    lines.extend(_report_text(row, detailed=False) for row in rows)
    lines.append("\nПодробнее: <code>/report_info ID</code> · закрыть: <code>/report_done ID комментарий</code>")
    await message.reply("\n\n".join(lines))


@router.message(Command("report_info"))
async def report_info_cmd(message: Message):
    if not await _require_permission(message, "reports_view", "помощник или выше"):
        return
    raw = _arg(message).split(maxsplit=1)[0] if _arg(message) else ""
    if not raw.isdigit():
        await message.reply("Использование: <code>/report_info ID</code>")
        return
    row = await GroupReportManager.get(int(raw), message.chat.id)
    if not row:
        await message.reply("Жалоба не найдена в этой группе.")
        return
    await message.reply(_report_text(row, detailed=True))


async def _close_report(message: Message, status: str) -> None:
    if not await _require_permission(message, "reports_manage", "модератор или выше") or not message.from_user:
        return
    raw = _arg(message)
    parts = raw.split(maxsplit=1) if raw else []
    if not parts or not parts[0].isdigit():
        command = "/report_done" if status == "resolved" else "/report_reject"
        await message.reply(f"Использование: <code>{command} ID комментарий</code>")
        return
    report_id = int(parts[0])
    resolution = parts[1] if len(parts) > 1 else ("Рассмотрено администрацией" if status == "resolved" else "Отклонено администрацией")
    row = await GroupReportManager.close(
        report_id,
        chat_id=message.chat.id,
        handled_by=message.from_user.id,
        status=status,
        resolution=resolution,
    )
    if not row:
        await message.reply("Жалоба не найдена в этой группе.")
        return
    await AuditLogManager.add(message.chat.id, message.from_user.id, f"report_{status}", resolution[:500], row.target_id, int(time.time()))
    await message.reply(("✅ Жалоба закрыта." if status == "resolved" else "⚪ Жалоба отклонена.") + f" <b>#{row.id}</b>")
    try:
        await message.bot.send_message(
            row.reporter_id,
            f"🚨 Жалоба <b>#{row.id}</b> рассмотрена. Статус: <b>{'решена' if status == 'resolved' else 'отклонена'}</b>.\n"
            f"Комментарий: {html.escape(resolution[:700])}",
        )
    except Exception:
        pass


@router.message(Command("report_done"))
async def report_done_cmd(message: Message):
    await _close_report(message, "resolved")


@router.message(Command("report_reject"))
async def report_reject_cmd(message: Message):
    await _close_report(message, "rejected")



@router.message(Command("modlog"))
async def modlog_cmd(message: Message):
    if not await _require_permission(message, "modlog", "модератор или выше"):
        return
    rows = await GroupAuditManager.recent(message.chat.id, 12)
    if not rows:
        await message.reply("📜 Журнал модерации пока пуст.")
        return
    lines = ["📜 <b>Последние действия модерации</b>"]
    for row in rows:
        when = datetime.fromtimestamp(row.created_at or 0, tz=timezone.utc).strftime("%d.%m %H:%M")
        target = f" → <code>{row.target_id}</code>" if row.target_id else ""
        details = f" · {html.escape((row.details or '')[:180])}" if row.details else ""
        lines.append(f"• {when} · <b>{html.escape(row.action)}</b>{target}{details}")
    await message.reply("\n".join(lines))


@router.message(Command("recovery"))
async def recovery_cmd(message: Message):
    if not message.from_user or not settings.owner_id or not is_owner(message.from_user.id):
        await message.reply("Эта диагностика доступна только главному владельцу.")
        return
    rows = await recovery_runtime.recent(10)
    if not rows:
        await message.reply("🩺 Журнал автоматического восстановления пуст. Это хороший знак.")
        return
    lines = ["🩺 <b>Автовосстановление Kira</b>"]
    for row in rows:
        icon = "✅" if row.recovered else "⚠️"
        when = datetime.fromtimestamp(row.created_at or 0, tz=timezone.utc).strftime("%d.%m %H:%M")
        lines.append(
            f"{icon} {when} · <code>{html.escape(row.category)}</code> · "
            f"{html.escape((row.action or 'наблюдение')[:220])}"
        )
    await message.reply("\n".join(lines))
