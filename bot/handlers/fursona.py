from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.prompt_translate import is_minor_request
from bot.rp_engine import CharacterLibrary

router = Router(name="fursona")
CARD_NAME = "фурсона"  # reserved name in the user's character library
MAX_LEN = 400

HELP = (
    "🦊 <b>Твоя фурсона</b>\n"
    "Задай внешность один раз — и рисуй её в любых сценах.\n"
    "• <code>/fursona рыжая лиса, белая грудь, зелёные глаза, шарф</code> — сохранить\n"
    "• <code>/fursona</code> — показать · <code>/fursona clear</code> — удалить\n"
    "• <code>/me_image сидит у костра ночью, стиль:акварель, формат:портрет</code> — нарисовать её\n"
    "Описание подставляется и в <code>/rp me</code> командой <code>/fursona rp</code>."
)


def _strip(message: Message, names: str) -> str:
    return re.sub(rf"(?i)^(?:/(?:{names})(?:@\w+)?|фурсона|я картинка)\s*", "", message.text or "").strip()


@router.message(Command("fursona"))
@router.message(F.text.regexp(r"(?i)^фурсона(?:\s|$)"))
async def fursona_cmd(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    raw = _strip(message, "fursona")
    low = raw.lower()
    current = await CharacterLibrary.get(uid, CARD_NAME)
    if low in {"clear", "удалить", "сброс"}:
        await CharacterLibrary.save(uid, CARD_NAME, "—")  # "—" marks "no fursona"
        await message.reply("🧹 Фурсона удалена.")
        return
    if low == "rp":
        if not current or current == "—":
            await message.reply("Сначала задай фурсону: <code>/fursona описание</code>")
            return
        from bot.rp_engine import RPStore
        await RPStore.update(uid, message.chat.id, user_char=current)
        await message.reply("🎭 Фурсона записана как твой персонаж в RP (<code>/rp status</code>).")
        return
    if not raw:
        if current and current != "—":
            await message.reply(f"🦊 <b>Твоя фурсона:</b>\n{html.escape(current)}\n\nНарисовать: <code>/me_image сцена</code>")
        else:
            await message.reply(HELP)
        return
    if is_minor_request(raw):
        await message.reply("Персонажи младше 18 лет не поддерживаются.")
        return
    await CharacterLibrary.save(uid, CARD_NAME, raw[:MAX_LEN])
    await message.reply(f"💾 Фурсона сохранена:\n{html.escape(raw[:MAX_LEN])}\n\nРисуй: <code>/me_image сцена</code>")


@router.message(Command("me_image"))
@router.message(F.text.regexp(r"(?i)^я\s+картинка(?:\s|$)"))
async def me_image_cmd(message: Message):
    if not message.from_user:
        return
    from bot.handlers.suite import _image_generation_impl  # late import: suite is a heavy module

    card = await CharacterLibrary.get(message.from_user.id, CARD_NAME)
    if not card or card == "—":
        await message.reply("Сначала опиши свою фурсону: <code>/fursona рыжая лиса, зелёные глаза</code>")
        return
    scene = _strip(message, "me_image") or "портрет, расслабленная поза"
    await _image_generation_impl(message, f"{card}, {scene}")
