import html
import random
import time
from asyncio import sleep
from contextlib import suppress
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core import fetch_user
from bot.handlers.commands import cmd_manager
from bot.locale import _, format_seconds
from bot.sql import UserManager

router = Router()

COOLDOWN_SECONDS = 3600

# Защита от двойного запуска, пока идёт мини-сцена.
_active_masturbation_users: set[int] = set()
MASTURBATE_TRIGGER = "\u0434\u0440\u043e\u0447"
TOP_PENIS_COMMANDS = (
    "\u0442\u043e\u043f \u0447\u043b\u0435\u043d",
    "\u0442\u043e\u043f \u043f\u0435\u043d\u0438\u0441",
    "\u0442\u043e\u043f \u0445\u0443\u0439",
    "\u0442\u043e\u043f \u0434\u0440\u043e\u0447",
)


TAIL_TRIGGER = "виляй"
TOP_TAIL_COMMANDS = (
    "топ хвост",
    "топ хвостов",
    "топ пушистость",
)



def _masturbate_side_effect() -> tuple[str, str, int]:
    """Comedic post-game effect; intentionally non-graphic."""
    roll = random.random()
    if roll < 0.08:
        return "motivation", "🫠 <b>Эпическая побочка:</b> мотивация временно покинула чат. Нужен небольшой отдых.", 900
    if roll < 0.20:
        return "sleepy", "😴 <b>Побочка:</b> накрыла сонливость. Кира прописала виртуальный плед.", 600
    if roll < 0.31:
        return "thirsty", "🥤 <b>Побочка:</b> появилась жажда. Виртуальная вода уже на столе.", 180
    if roll < 0.39:
        return "second_wind", "⚡ <b>Редкое событие:</b> второе дыхание! Дополнительного штрафа к кулдауну нет.", 0
    if roll < 0.45:
        return "zen", "🏆 <b>Редкое событие:</b> абсолютное спокойствие. Кира подозрительно впечатлена.", 0
    return "calm", "✨ <b>Эффект:</b> без необычных последствий.", 0

@cmd_manager.register(MASTURBATE_TRIGGER, _("droch_description"))
@router.message(F.text.lower().startswith(MASTURBATE_TRIGGER))
async def masturbate_handle(message: Message) -> None:
    if message.chat.type == "private" or not message.from_user:
        return

    user_id = message.from_user.id
    user = await UserManager.get(user_id)
    now = int(time.time())
    cooldown_until = int(user.masturbate_cooldown_until or 0)

    if cooldown_until > now:
        wait_seconds = cooldown_until - now
        cooldown_message = await message.reply(
            _("wait_cooldown_droch", expired_at=format_seconds(wait_seconds))
        )
        await sleep(10)
        for msg in (cooldown_message, message):
            with suppress(Exception):
                await msg.delete()
        return

    if user_id in _active_masturbation_users:
        await message.reply("🍌 Ты уже занят этим делом. Дай себе закончить 😏")
        return

    _active_masturbation_users.add(user_id)
    name = html.escape(message.from_user.full_name[:80])
    progress = await message.reply(
        f"🍌 <b>{name}</b> начал дрочить…\n"
        "▰▱▱▱▱ 10%"
    )

    stages = (
        ("😏 Вошёл в ритм…", "▰▰▱▱▱ 35%"),
        ("🔥 Процесс идёт полным ходом…", "▰▰▰▱▱ 60%"),
        ("💦 Уже близко к финишу…", "▰▰▰▰▱ 85%"),
        ("✨ Почти закончил…", "▰▰▰▰▰ 100%"),
    )

    try:
        for status, bar in stages:
            await sleep(random.uniform(1.4, 2.4))
            with suppress(Exception):
                await progress.edit_text(
                    f"🍌 <b>{name}</b> дрочит…\n{status}\n{bar}"
                )

        # Результат считается только ПОСЛЕ завершения мини-сцены.
        user = await UserManager.get(user_id)
        penis = round(float(user.penis_len or 0), 2)
        chance = random.randint(1, 7)

        if chance == 7 and penis > 0:
            raw_delta = round(random.uniform(1, 3), 2)
            updated_penis = round(max(0.0, penis - raw_delta), 2)
            result_text = _("cutted_penis", penis=updated_penis, rand_num=raw_delta)
        else:
            delta = round(random.uniform(0, 3), 2)
            updated_penis = round(penis + delta, 2)
            result_text = _("grown_penis", penis=updated_penis, rand_num=delta)

        effect_key, side_effect, extra_cooldown = _masturbate_side_effect()
        await UserManager.update_masturbate_stats(
            user_id,
            penis_len=updated_penis,
            cooldown_until=int(time.time()) + COOLDOWN_SECONDS + extra_cooldown,
            effect=f"droch:{effect_key}", effect_until=int(time.time()) + max(900, extra_cooldown),
        )
        await progress.edit_text(
            f"✅ <b>{name} закончил.</b>\n\n{result_text}\n\n{side_effect}"
        )
    except Exception:
        # Не ставим кулдаун, если процесс оборвался до записи результата.
        with suppress(Exception):
            await progress.edit_text("😵 Процесс неожиданно прервался. Попробуй ещё раз.")
        raise
    finally:
        _active_masturbation_users.discard(user_id)


@cmd_manager.register("\u0442\u043e\u043f \u0434\u0440\u043e\u0447", _("top_penis_description"))
@router.message(F.text.lower().in_(TOP_PENIS_COMMANDS))
async def show_top_penis(message: Message) -> None:
    if message.chat.type == "private":
        return

    progress = await message.reply(_("calc_users_penis"))
    top = await UserManager.get_top_penis()


    if not top:
        await progress.delete()
        await message.reply(_("no_penises"))
        return

    rows: list[str] = []
    hist_data: list[SimpleNamespace] = []
    for index, user in enumerate(top, start=1):
        user_tag = f'<a href="tg://user?id={user.user_id}">{user.user_id}</a>'
        display_name = str(user.user_id)
        try:
            member = await message.bot.get_chat_member(message.chat.id, user.user_id)
            user_tag = fetch_user(member.user)
            display_name = member.user.full_name
        except (TelegramBadRequest, TelegramForbiddenError):
            pass

        rows.append(f"{index}. {user_tag} \u2014 <b>{user.penis_len:.2f}</b>")
        hist_data.append(SimpleNamespace(name=display_name, leng=float(user.penis_len)))

    names = "\n".join(rows)
    caption = _("top_penis_message", names=names)

    try:
        from bot.hist import create_hist_penis

        hist = create_hist_penis(hist_data)
        await message.reply_photo(
            photo=BufferedInputFile(hist, filename="top.png"),
            caption=caption,
        )
        await progress.delete()
    except Exception:
        await message.reply(caption)


@cmd_manager.register(TAIL_TRIGGER, _("tail_description"))
@router.message(F.text.lower().startswith(TAIL_TRIGGER))
async def tail_handle(message: Message) -> None:
    if message.chat.type == "private" or not message.from_user:
        return

    user = await UserManager.get(message.from_user.id)
    now = int(time.time())
    cooldown_until = int(user.tail_cooldown_until or 0)

    if cooldown_until > now:
        wait_seconds = cooldown_until - now
        cooldown_message = await message.reply(_("tail_wait_cooldown", expired_at=format_seconds(wait_seconds)))
        await sleep(10)
        for msg in (cooldown_message, message):
            with suppress(Exception):
                await msg.delete()
        return

    builder = InlineKeyboardBuilder()
    builder.button(text=_("tail_btn"), callback_data=f"tail:{message.from_user.id}")
    await message.reply(_("tail_wag_response"), reply_markup=builder.as_markup())


@cmd_manager.register("топ хвост", _("top_tail_description"))
@router.message(F.text.lower().in_(TOP_TAIL_COMMANDS))
async def show_top_tails(message: Message) -> None:
    if message.chat.type == "private":
        return

    progress = await message.reply(_("calc_tails"))
    top = await UserManager.get_top_tails()
    if not top:
        await progress.delete()
        await message.reply(_("no_tails"))
        return

    rows: list[str] = []
    for index, user in enumerate(top, start=1):
        user_tag = f'<a href="tg://user?id={user.user_id}">{user.user_id}</a>'
        try:
            member = await message.bot.get_chat_member(message.chat.id, user.user_id)
            user_tag = fetch_user(member.user)
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        rows.append(f"{index}. {user_tag} — <b>{float(user.tail_fluff):.2f}</b> см")
    await progress.delete()
    await message.reply(_("top_tails_message", names="\n".join(rows)))
