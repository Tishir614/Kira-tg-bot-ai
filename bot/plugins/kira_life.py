from __future__ import annotations

import hashlib
import html
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers.commands import cmd_manager
from bot.sql import UserManager

router = Router(name="kira-life-1.9")

EFFECTS = {
    "drink:sofa": "🛋 Спит на виртуальном диване",
    "drink:wobbly": "🥴 Немного штормит",
    "drink:karaoke": "🎤 Караоке-режим",
    "drink:pizza": "🍕 Охота за пиццей",
    "drink:water": "💧 Водный баланс восстановлен",
    "drink:calm": "✨ Спокойная посиделка",
    "droch:motivation": "🫠 Мотивация ушла погулять",
    "droch:sleepy": "😴 Сонливость",
    "droch:thirsty": "🥤 Жажда",
    "droch:second_wind": "⚡ Второе дыхание",
    "droch:zen": "🏆 Абсолютное спокойствие",
    "droch:calm": "✨ Без необычных последствий",
}


def _kira_state(chat_id: int) -> tuple[str, str, int]:
    now = datetime.now()
    bucket = now.strftime("%Y-%m-%d-%H")
    seed = int(hashlib.sha256(f"{chat_id}:{bucket}:kira-life".encode()).hexdigest()[:8], 16)
    moods = ["😸 игривая", "☕ уютная", "⚡ энергичная", "🌙 задумчивая", "🦊 любопытная", "🎧 музыкальная"]
    jobs = ["читает чат", "сортирует мемы", "слушает музыку", "охраняет сервер", "считает виртуальные монетки", "ищет новую пасхалку"]
    return moods[seed % len(moods)], jobs[(seed // 7) % len(jobs)], 45 + seed % 56


@cmd_manager.register("жизнь киры", "Показать настроение, энергию и текущее занятие Киры.")
@router.message(Command("kira_life"))
@router.message(F.text.lower().in_({"жизнь киры", "кира жизнь", "кира что делаешь", "кира что ты делаешь"}))
async def kira_life(message: Message) -> None:
    mood, activity, energy = _kira_state(message.chat.id)
    await message.reply(
        "🦊 <b>Жизнь Киры</b>\n"
        f"Настроение: <b>{mood}</b>\n"
        f"Энергия: <b>{energy}%</b>\n"
        f"Сейчас: <b>{activity}</b>\n\n"
        "Состояние меняется в течение дня и зависит от текущего чата."
    )


@cmd_manager.register("эффекты", "Показать активную игровую побочку пользователя.")
@router.message(Command("effects"))
@router.message(F.text.lower().in_({"эффекты", "мои эффекты", "побочки", "мои побочки"}))
async def effects(message: Message) -> None:
    if not message.from_user:
        return
    user = await UserManager.get(message.from_user.id)
    key = str(getattr(user, "active_effect", "") or "")
    until = int(getattr(user, "active_effect_until", 0) or 0)
    now = int(time.time())
    if not key or until <= now:
        await message.reply("✨ Активных игровых эффектов сейчас нет.")
        return
    left = until - now
    mins, secs = divmod(left, 60)
    label = EFFECTS.get(key, html.escape(key))
    await message.reply(f"🧪 <b>Активный эффект</b>\n{label}\nОсталось: <b>{mins}м {secs}с</b>")


@router.message(F.text.lower().in_({"кира секрет", "секрет киры"}))
async def secret(message: Message) -> None:
    mood, _, energy = _kira_state(message.chat.id)
    if energy >= 90:
        await message.reply("🥚 <b>Секрет найден!</b> Сегодня у Киры избыток энергии. Кодовое имя события: «Лисий разгон» 🦊⚡")
    else:
        await message.reply(f"🥚 Кира посмотрела подозрительно. Секрет сегодня не открылся. Настроение: {mood}")
