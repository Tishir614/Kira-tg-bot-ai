import html
import random
import time
from asyncio import sleep
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from bot.core import fetch_user

from bot.handlers.commands import cmd_manager
from bot.sql import UserManager

router = Router(name="alcohol_game")
COOLDOWN_SECONDS = 3600
DRINK_TRIGGER = "выпить"
TOP_COMMANDS = ("топ алкоголизм", "топ выпивох", "топ алкоголь")
_active_users: set[int] = set()


def _bar(value: float) -> str:
    value = max(0.0, min(100.0, value))
    filled = min(10, int(round(value / 10)))
    return "▰" * filled + "▱" * (10 - filled)



def _side_effect(score: float) -> tuple[str, str, int]:
    """Return a playful non-medical side effect and extra cooldown seconds."""
    roll = random.random()
    if score >= 80 and roll < 0.22:
        return "sofa", "🛋 <b>Побочка:</b> виртуально уснул на диване. Бар закроется подольше.", 900
    if score >= 55 and roll < 0.38:
        return "wobbly", "🥴 <b>Побочка:</b> режим «пол подозрительно качается».", 600
    if roll < 0.12:
        return "karaoke", "🎤 <b>Редкое событие:</b> внезапно открылся талант караоке. Соседи не подтвердили.", 0
    if roll < 0.24:
        return "pizza", "🍕 <b>Побочка:</b> появился легендарный аппетит. +0 к пользе, +100 к желанию пиццы.", 180
    if roll < 0.34:
        return "water", "💧 <b>Удача:</b> Кира вручила виртуальный стакан воды. Сегодня без дополнительных эффектов.", 0
    return "calm", "✨ <b>Эффект:</b> посиделка прошла без приключений.", 0

def _rank(value: float) -> str:
    if value < 10:
        return "🥤 Трезвый новичок"
    if value < 30:
        return "🍺 Любитель посиделок"
    if value < 55:
        return "🍻 Барный исследователь"
    if value < 80:
        return "🥴 Штормит"
    return "🫠 Легенда алкошкалы"


@cmd_manager.register(DRINK_TRIGGER, "Игровая алкошкала: мини-сцена и случайное изменение рейтинга. Это не реальный уровень алкоголя.")
@router.message(F.text.lower().startswith(DRINK_TRIGGER))
async def drink_handle(message: Message) -> None:
    if message.chat.type == "private" or not message.from_user:
        return
    uid = message.from_user.id
    user = await UserManager.get(uid)
    now = int(time.time())
    cooldown = int(user.alcohol_cooldown_until or 0)
    if cooldown > now:
        left = cooldown - now
        mins, secs = divmod(left, 60)
        msg = await message.reply(f"🧃 Бар пока закрыт для тебя. Возвращайся через {mins}м {secs}с.")
        await sleep(8)
        for item in (msg, message):
            with suppress(Exception):
                await item.delete()
        return
    if uid in _active_users:
        await message.reply("🍻 Ты уже участвуешь в мини-сцене. Сначала допей виртуальный стакан 😄")
        return

    _active_users.add(uid)
    name = html.escape(message.from_user.full_name[:80])
    progress = await message.reply(f"🍹 <b>{name}</b> решил выпить…\n▰▱▱▱▱ 10%")
    stages = (
        ("🍺 Первый виртуальный глоток…", "▰▰▱▱▱ 35%"),
        ("🎵 Музыка внезапно стала лучше…", "▰▰▰▱▱ 60%"),
        ("🥴 Пол слегка подозрительный…", "▰▰▰▰▱ 85%"),
        ("🍻 Посиделка завершена!", "▰▰▰▰▰ 100%"),
    )
    try:
        for status, bar in stages:
            await sleep(random.uniform(1.0, 1.8))
            with suppress(Exception):
                await progress.edit_text(f"🍹 <b>{name}</b> выпивает…\n{status}\n{bar}")

        user = await UserManager.get(uid)
        old = float(user.alcohol_score or 0.0)
        # Игровой рейтинг, не BAC и не медицинский показатель.
        if random.randint(1, 8) == 8 and old > 0:
            delta = round(random.uniform(1.0, 6.0), 1)
            new = round(max(0.0, old - delta), 1)
            change = f"🧊 Внезапно протрезвел на <b>{delta:.1f}</b> пункта."
        else:
            delta = round(random.uniform(2.0, 12.0), 1)
            new = round(min(100.0, old + delta), 1)
            change = f"🍺 Алкошкала выросла на <b>{delta:.1f}</b> пункта."

        effect_key, side_effect, extra_cooldown = _side_effect(new)
        await UserManager.update_alcohol_stats(
            uid, alcohol_score=new, cooldown_until=int(time.time()) + COOLDOWN_SECONDS + extra_cooldown,
            effect=f"drink:{effect_key}", effect_until=int(time.time()) + max(900, extra_cooldown)
        )
        await progress.edit_text(
            f"✅ <b>{name} закончил виртуальную посиделку.</b>\n\n"
            f"{change}\n{_bar(new)} <b>{new:.1f}/100</b>\n{_rank(new)}\n\n"
            f"{side_effect}\n\n"
            "<i>Алкошкала игровая и не показывает реальное опьянение.</i>"
        )
    except Exception:
        with suppress(Exception):
            await progress.edit_text("😵 Виртуальный бар завис. Результат не записан, попробуй ещё раз.")
        raise
    finally:
        _active_users.discard(uid)


@cmd_manager.register("топ алкоголизм", "Показать игровой топ алкошкалы.")
@router.message(F.text.lower().in_(TOP_COMMANDS))
async def alcohol_top(message: Message) -> None:
    if message.chat.type == "private":
        return
    top = await UserManager.get_top_alcohol()
    if not top:
        await message.reply("🍹 Алкошкала пока пустая. Напиши «выпить», чтобы открыть виртуальный бар.")
        return
    rows = []
    for i, user in enumerate(top, 1):
        user_tag = f'<a href="tg://user?id={user.user_id}">{user.user_id}</a>'
        try:
            member = await message.bot.get_chat_member(message.chat.id, user.user_id)
            user_tag = fetch_user(member.user)
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        rows.append(f'{i}. {user_tag} — <b>{user.alcohol_score:.1f}/100</b>')
    await message.reply("🍻 <b>Топ алкошкалы</b>\n\n" + "\n".join(rows))
