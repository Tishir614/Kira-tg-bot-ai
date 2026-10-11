from __future__ import annotations

import html
import json
import os
import re
import time

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.ai_client import ai
from bot.image_generation import image_generator
from bot.kira_next import AdminIntent, ChatMemoryManager, LongTermMemoryManager, PrivacyManager
from bot.sql import ChatSettingsManager, session_factory
from bot.sql.orm_tables import PendingAdminAction

router = Router(name="kira-1.0")


def _arg(message: Message) -> str:
    if not message.text:
        return ""
    parts = message.text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


async def _is_admin(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


@router.message(Command("memory"))
async def memory_cmd(message: Message):
    if not message.from_user:
        return
    rows = await LongTermMemoryManager.list(message.from_user.id, message.chat.id)
    privacy = await PrivacyManager.get(message.from_user.id)
    body = "\n".join(
        f"• <b>{html.escape(row.key or row.kind)}</b>: {html.escape(row.value[:500])}"
        for row in rows[:20]
    ) or "Пока нет сохранённых фактов."
    await message.reply(
        "🧠 <b>Память Киры</b>\n"
        f"Личная память: {'✅' if privacy.personal_memory else '❌'} · "
        f"история групп: {'✅' if privacy.allow_group_history else '❌'}\n\n"
        f"{body}\n\nДобавить: <code>/запомнить любимый цвет = фиолетовый</code>"
    )


@router.message(Command("remember"))
async def remember_cmd(message: Message):
    if not message.from_user:
        return
    raw = _arg(message)
    if not raw:
        await message.reply("Использование: <code>/запомнить ключ = значение</code>")
        return
    if "=" in raw:
        key, value = raw.split("=", 1)
    else:
        key, value = "заметка", raw
    await LongTermMemoryManager.remember(
        message.from_user.id, message.chat.id, "preference", key.strip(), value.strip(), 70
    )
    await message.reply("🧠 Запомнила.")


@router.message(Command("privacy"))
async def privacy_cmd(message: Message):
    if not message.from_user:
        return
    raw = _arg(message).casefold()
    if raw.startswith(("personal ", "личная ")):
        await PrivacyManager.update(
            message.from_user.id,
            personal_memory=raw.endswith(("on", "вкл", "включить", "да")),
        )
    elif raw.startswith(("groups ", "группы ")):
        await PrivacyManager.update(
            message.from_user.id,
            allow_group_history=raw.endswith(("on", "вкл", "включить", "да")),
        )
    elif raw.startswith(("chat ", "чат ")) and await _is_admin(message):
        await ChatMemoryManager.update_settings(
            message.chat.id,
            enabled=raw.endswith(("on", "вкл", "включить", "да")),
        )
    privacy = await PrivacyManager.get(message.from_user.id)
    cfg = await ChatMemoryManager.settings(message.chat.id)
    await message.reply(
        "🔐 <b>Приватность</b>\n"
        f"Личная память: {'✅' if privacy.personal_memory else '❌'}\n"
        f"Мои сообщения в памяти групп: {'✅' if privacy.allow_group_history else '❌'}\n"
        f"Память этого чата: {'✅' if cfg.enabled else '❌'}\n\n"
        "<code>/приватность личная вкл|выкл</code>\n"
        "<code>/приватность группы вкл|выкл</code>\n"
        "Админ: <code>/приватность чат вкл|выкл</code>"
    )


@router.message(Command("forget_me"))
async def forget_me_cmd(message: Message):
    if not message.from_user:
        return
    if _arg(message).casefold() not in {"confirm", "подтверждаю", "yes"}:
        await message.reply(
            "⚠️ Это удалит долговременную память Киры о тебе и твои сообщения из памяти групп. "
            "Подтверждение: <code>/забыть_меня подтверждаю</code>"
        )
        return
    result = await PrivacyManager.forget_user(message.from_user.id)
    await message.reply(
        f"🧹 Данные памяти удалены: фактов {result['long_term']}, сообщений {result['history']}, "
        f"ников {result.get('nicknames', 0)}."
    )


@router.message(Command("find_memory"))
async def find_memory_cmd(message: Message):
    query = _arg(message)
    if not query:
        await message.reply("<code>/найти_память что обсуждали про сервер</code>")
        return
    rows = await ChatMemoryManager.search(message.chat.id, query, 8)
    if not rows:
        await message.reply("Ничего похожего в сохранённой истории не нашла.")
        return
    await message.reply(
        "🔎 <b>Нашла в памяти чата</b>\n\n"
        + "\n\n".join(
            f"• {html.escape(row.display_name)}: {html.escape(row.text[:650])}" for row in rows
        )
    )


@router.message(Command("digest"))
async def digest_cmd(message: Message):
    raw = _arg(message).lower() or "24h"
    match = re.search(r"(\d+)\s*([hdчд])", raw)
    seconds = 86400
    if match:
        seconds = min(7 * 86400, int(match.group(1)) * (3600 if match.group(2) in {"h", "ч"} else 86400))
    rows = await ChatMemoryManager.recent(message.chat.id, int(time.time()) - seconds, 1200)
    if not rows:
        await message.reply(
            "📰 За этот период в памяти чата нет сообщений. Админ может включить её: "
            "<code>/приватность чат вкл</code>"
        )
        return
    text = "\n".join(f"{row.display_name}: {row.text[:500]}" for row in rows)
    prompt = (
        "Сделай компактную сводку Telegram-группы: важные темы, решения, ссылки/ресурсы, "
        "конфликты без драматизации, новые события и что требует внимания. Не выдумывай.\n\n"
        + text[-28000:]
    )
    try:
        answer = await ai.respond(
            prompt,
            user_id=message.from_user.id if message.from_user else 0,
            chat_id=message.chat.id,
            remember=False,
            max_tokens=1100,
        )
    except Exception:
        answer = "\n".join(f"• {row.display_name}: {row.text[:250]}" for row in rows[-20:])
    await message.reply("📰 <b>Сводка</b>\n" + html.escape(answer[:3900]))


@router.message(Command("summary_voice"))
async def summary_voice_cmd(message: Message):
    reply = message.reply_to_message
    if not reply or not (reply.voice or reply.audio):
        await message.reply("Ответь <code>/сводка_голоса</code> на голосовое сообщение.")
        return
    media = reply.voice or reply.audio
    file = await message.bot.get_file(media.file_id)
    bio = await message.bot.download_file(file.file_path)
    try:
        transcript = await ai.transcribe(
            bio.read(),
            filename=getattr(media, "file_name", None) or "voice.ogg",
            mime_type=getattr(media, "mime_type", None) or "audio/ogg",
        )
        answer = await ai.respond(
            "Суммируй расшифровку в 3-8 полезных пунктов и отдельно выдели решения/задачи, если они есть:\n"
            + transcript,
            user_id=message.from_user.id if message.from_user else 0,
            chat_id=message.chat.id,
            remember=False,
            max_tokens=800,
        )
        await message.reply("🎙️ <b>Сводка голосового</b>\n" + html.escape(answer[:3800]))
    except Exception as exc:
        await message.reply("Не удалось обработать голосовое: " + html.escape(str(exc)[:300]))


@router.message(Command("personality"))
async def personality_cmd(message: Message):
    cfg = await ChatMemoryManager.settings(message.chat.id)
    raw = _arg(message).lower()
    aliases = {
        "обычная": "normal",
        "normal": "normal",
        "дружелюбная": "friendly",
        "friendly": "friendly",
        "серьёзная": "serious",
        "serious": "serious",
        "юмор": "humorous",
        "юмористическая": "humorous",
        "humorous": "humorous",
        "rp": "rp",
    }
    if raw and await _is_admin(message) and raw in aliases:
        cfg = await ChatMemoryManager.update_settings(message.chat.id, personality=aliases[raw])
    await message.reply(
        f"🎭 Характер Киры в этом чате: <b>{html.escape(cfg.personality)}</b>\n"
        "Админ: <code>/характер дружелюбная|серьезная|юмористическая|обычная|rp</code>"
    )


@router.message(Command("aimod"))
async def aimod_cmd(message: Message):
    if not await _is_admin(message):
        return
    parts = _arg(message).split()
    cfg = await ChatMemoryManager.settings(message.chat.id)
    mode_aliases = {"off": "off", "выкл": "off", "assist": "assist", "совет": "assist", "auto": "auto", "авто": "auto"}
    if parts and parts[0] in mode_aliases:
        strictness = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else cfg.moderator_strictness
        cfg = await ChatMemoryManager.update_settings(
            message.chat.id,
            moderator_mode=mode_aliases[parts[0]],
            moderator_strictness=max(1, min(5, strictness)),
        )
    await message.reply(
        f"🛡️ AI-модератор: <b>{cfg.moderator_mode}</b>, строгость {cfg.moderator_strictness}/5\n"
        "<code>/ии_модератор совет 3</code> — советует\n"
        "<code>/ии_модератор авто 4</code> — удаляет только при высокой уверенности\n"
        "<code>/ии_модератор выкл</code>"
    )


@router.message(Command("admin_ai"))
async def admin_ai_cmd(message: Message):
    if not await _is_admin(message) or not message.from_user:
        return
    request = _arg(message)
    if not request:
        await message.reply("Пример: <code>/ии_админ запрети ссылки и включи ИИ-модерацию</code>")
        return
    row = await AdminIntent.propose(message.chat.id, message.from_user.id, request)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[ 
            InlineKeyboardButton(text="✅ Применить", callback_data=f"k10apply:{row.id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"k10cancel:{row.id}"),
        ]]
    )
    await message.reply(
        "🤖 <b>Предлагаемые изменения</b>\n"
        + html.escape(row.human_summary)
        + "\n\nНичего не меняю без подтверждения.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("k10apply:"))
async def apply_admin_action(callback):
    if not callback.message or not callback.from_user:
        return
    action_id = int(callback.data.split(":", 1)[1])
    async with session_factory() as session:
        row = await session.get(PendingAdminAction, action_id)
        if not row or row.status != "pending" or row.admin_id != callback.from_user.id:
            await callback.answer("Предложение недоступно", show_alert=True)
            return
        data = json.loads(row.action_json or "{}")
        memory_values = {
            key: value
            for key, value in {
                "moderator_mode": data.get("moderator_mode"),
                "moderator_strictness": data.get("moderator_strictness"),
                "enabled": data.get("memory_enabled"),
                "retention_days": data.get("retention_days"),
                "personality": data.get("personality"),
                "speech_style": data.get("speech_style"),
            }.items()
            if value is not None
        }
        if memory_values:
            await ChatMemoryManager.update_settings(row.chat_id, **memory_values)
        if data.get("links_allowed") is not None:
            await ChatSettingsManager.update(row.chat_id, links_allowed=bool(data["links_allowed"]))
        row.status = "applied"
        summary = row.human_summary
        await session.commit()
    await callback.message.edit_text("✅ Настройки применены.\n" + html.escape(summary))
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("k10cancel:"))
async def cancel_admin_action(callback):
    action_id = int(callback.data.split(":", 1)[1])
    async with session_factory() as session:
        row = await session.get(PendingAdminAction, action_id)
        if row and row.admin_id == callback.from_user.id:
            row.status = "cancelled"
            await session.commit()
    if callback.message:
        await callback.message.edit_text("❌ Изменения отменены.")
    await callback.answer()


async def _text_tool(message: Message, instruction: str) -> None:
    text = _arg(message)
    if not text and message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not text:
        await message.reply("Передай текст после команды или ответь командой на сообщение.")
        return
    try:
        result = await ai.respond(
            instruction + "\n\n" + text,
            user_id=message.from_user.id if message.from_user else 0,
            chat_id=message.chat.id,
            remember=False,
            max_tokens=1000,
        )
    except Exception as exc:
        await message.reply(html.escape(str(exc)[:500]))
        return
    await message.reply(html.escape(result[:3900]))


@router.message(Command("rewrite"))
async def rewrite_cmd(message: Message):
    await _text_tool(message, "Перепиши красиво и естественно, сохрани смысл. Верни только готовый текст.")


@router.message(Command("fixtext"))
async def fixtext_cmd(message: Message):
    await _text_tool(message, "Исправь орфографию, пунктуацию и стиль. Верни только исправленный текст.")


@router.message(Command("translate"))
async def translate_cmd(message: Message):
    await _text_tool(message, "Переведи текст на русский, если он не русский; если русский — на естественный английский. Верни только перевод.")


@router.message(Command("congrats"))
async def congrats_cmd(message: Message):
    await _text_tool(message, "Сделай тёплое, живое поздравление без канцелярита. Верни только поздравление.")


@router.message(Command("avatar"))
async def avatar_cmd(message: Message):
    prompt = _arg(message) or "stylish profile avatar, centered portrait, expressive face"
    result = await image_generator.generate("profile avatar, square composition, " + prompt, kira=False)
    await message.reply_photo(BufferedInputFile(result.data, filename="avatar.png"), caption="✨ Локальный аватар")


@router.message(Command("meme"))
async def meme_cmd(message: Message):
    source = _arg(message)
    if not source and message.reply_to_message:
        source = message.reply_to_message.text or ""
    if not source:
        await message.reply("Напиши тему или ответь <code>/мем</code> на сообщение.")
        return
    try:
        prompt = await ai.respond(
            "Turn this chat line into a concise visual meme scene prompt. No text in image. Return only prompt:\n" + source,
            user_id=0,
            chat_id=0,
            remember=False,
            max_tokens=160,
        )
    except Exception:
        prompt = "funny reaction meme scene, " + source
    result = await image_generator.generate(prompt)
    await message.reply_photo(
        BufferedInputFile(result.data, filename="meme.png"),
        caption="🗿 Мем по мотивам сообщения\n" + html.escape(source[:500]),
    )


@router.message(Command("kira_app"))
async def kira_app_cmd(message: Message):
    url = os.getenv("KIRA_WEBAPP_URL", "").strip()
    if not url.startswith("https://"):
        legacy = os.getenv("DND_WEBAPP_URL", "").strip()
        help_url = os.getenv("HELP_URL", "").strip()
        if legacy.startswith("https://"):
            url = legacy[:-4] + "/kira" if legacy.endswith("/dnd") else legacy.rstrip("/") + "/kira"
        elif help_url.startswith("https://"):
            from urllib.parse import urlsplit
            parts = urlsplit(help_url)
            url = f"{parts.scheme}://{parts.netloc}/kira"
    if not url.startswith("https://"):
        await message.reply("🌐 Укажи <code>KIRA_WEBAPP_URL=https://твой-домен/kira</code> в .env.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🦊 Открыть Kira", web_app=WebAppInfo(url=url))]]
    )
    await message.reply(
        "🌐 <b>Kira Mini App 1.2</b>: профиль, магазин, D&D, команды, память и настройки в одном окне.",
        reply_markup=keyboard,
    )

@router.message(F.text.regexp(r"(?i)^кира[, ]+(?:что мы (?:решили|обсуждали)|найди (?:сообщение|где)|кто предложил)"))
async def natural_memory_question(message: Message):
    """Natural-language access to group memory, without memorizing another command."""
    if not message.text:
        return
    cfg = await ChatMemoryManager.settings(message.chat.id)
    if not cfg.enabled:
        await message.reply("🧠 Память этого чата выключена. Администратор может включить её: <code>/приватность чат вкл</code>.")
        return
    rows = await ChatMemoryManager.search(message.chat.id, message.text, 12)
    if not rows:
        await message.reply("Не нашла подходящих сообщений в сохранённой истории.")
        return
    evidence = "\n".join(
        f"[{row.display_name}] {row.text[:600]}" for row in rows
    )
    persona = {
        "normal": "Отвечай нейтрально и по делу.",
        "friendly": "Отвечай дружелюбно и тепло, но кратко.",
        "serious": "Отвечай строго, точно и без шуток.",
        "humorous": "Можно добавить лёгкую уместную шутку, не искажая факты.",
        "rp": "Сохраняй образ Киры, но факты из истории не выдумывай.",
    }.get(cfg.personality, "Отвечай дружелюбно.")
    prompt = (
        "Ответь на вопрос пользователя только на основе найденных сообщений. Если точного ответа нет, так и скажи. "
        + persona
        + "\nВОПРОС:\n" + message.text[:1600]
        + "\nНАЙДЕННАЯ ИСТОРИЯ:\n" + evidence[:20000]
    )
    try:
        answer = await ai.respond(
            prompt,
            user_id=message.from_user.id if message.from_user else 0,
            chat_id=message.chat.id,
            remember=False,
            max_tokens=800,
        )
        await message.reply("🧠 " + html.escape(answer[:3900]))
    except Exception:
        await message.reply(
            "🧠 Нашла похожее:\n\n"
            + "\n\n".join(f"• {html.escape(row.display_name)}: {html.escape(row.text[:500])}" for row in rows[:6])
        )
