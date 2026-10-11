from __future__ import annotations

import html
import os
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, MessageEntity

from bot.handlers.commands import cmd_manager

router = Router(name="kira-premium-emoji")

# Telegram custom emoji are rendered by Telegram itself. Kira does not grant a
# Premium subscription; she can relay custom emoji IDs that Telegram permits a bot to send.
_DEFAULT_EMOJI = {
    "лиса": "5368324170671202286",
    "сердце": "5368324170671202286",
}


def _configured() -> dict[str, str]:
    result = dict(_DEFAULT_EMOJI)
    raw = os.getenv("KIRA_CUSTOM_EMOJI", "")
    for part in raw.split(","):
        if "=" not in part:
            continue
        name, emoji_id = (x.strip() for x in part.split("=", 1))
        if name and re.fullmatch(r"\d{5,32}", emoji_id):
            result[name.casefold()] = emoji_id
    return result


async def _send_custom(message: Message, emoji_id: str, label: str = "✨") -> None:
    # The visible fallback character remains readable in clients that cannot render it.
    await message.answer(
        label,
        entities=[MessageEntity(type="custom_emoji", offset=0, length=len(label.encode("utf-16-le")) // 2, custom_emoji_id=emoji_id)],
    )


@cmd_manager.register("эмодзи", "Отправить доступный Кире Telegram custom emoji.")
@router.message(Command("emoji", "эмодзи"))
async def emoji_cmd(message: Message) -> None:
    items = _configured()
    arg = (message.text or "").split(maxsplit=1)
    if len(arg) == 1:
        await message.reply(
            "✨ <b>Эмодзи Киры</b>\n"
            "Использование: <code>/эмодзи название</code>\n"
            "Наборы: " + ", ".join(f"<code>{html.escape(x)}</code>" for x in sorted(items)) +
            "\n\nАдмин может добавить ID через <code>KIRA_CUSTOM_EMOJI=имя=id,имя2=id</code>."
        )
        return
    name = arg[1].strip().casefold()
    emoji_id = items.get(name)
    if not emoji_id:
        await message.reply("Такого эмодзи в наборе Киры пока нет. Напиши <code>/эмодзи</code>.")
        return
    try:
        await _send_custom(message, emoji_id)
    except Exception:
        await message.reply("✨ Этот custom emoji Telegram не разрешил отправить боту. Попробуй другой ID.")


@router.message(F.text.regexp(r"(?i)^кира[, ]+эмодзи\s+.+"))
async def emoji_phrase(message: Message) -> None:
    text = (message.text or "").strip()
    name = re.sub(r"(?i)^кира[, ]+эмодзи\s+", "", text).strip().casefold()
    emoji_id = _configured().get(name)
    if not emoji_id:
        return
    try:
        await _send_custom(message, emoji_id)
    except Exception:
        await message.reply("✨ Не получилось отправить этот custom emoji.")
