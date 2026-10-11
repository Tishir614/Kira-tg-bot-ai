import random
import time

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot.locale import _
from bot.sql import UserManager

router = Router()

COOLDOWN_SECONDS = 3600


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("masturbate:"))
async def masturbate_callback(call: CallbackQuery) -> None:
    """Совместимость со старыми сообщениями с кнопкой из прежних версий."""
    if not call.data or not call.from_user:
        return

    raw_target_id = call.data.split(":", maxsplit=1)[1]
    if not raw_target_id.isdigit() or call.from_user.id != int(raw_target_id):
        await call.answer(_("not_for_you"))
        return

    await call.answer(
        "🍌 Теперь кнопка не нужна. Просто напиши в чат: дроч",
        show_alert=True,
    )


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("tail:"))
async def tail_callback(call: CallbackQuery) -> None:
    if not call.data or not call.from_user or not isinstance(call.message, Message):
        return

    raw_target_id = call.data.split(":", maxsplit=1)[1]
    if not raw_target_id.isdigit():
        await call.answer()
        return

    target_id = int(raw_target_id)
    if call.from_user.id != target_id:
        await call.answer(_("not_for_you"))
        return

    user = await UserManager.get(target_id)
    tail = round(float(getattr(user, "tail_fluff", 0) or 0), 2)
    chance = random.randint(1, 6)

    if chance == 6 and tail > 0:
        raw_delta = round(random.uniform(0.5, 2.5), 2)
        updated_tail = round(max(0.0, tail - raw_delta), 2)
        text = _("tail_loss", tail=updated_tail, rand_num=raw_delta)
    else:
        delta = round(random.uniform(0.5, 3.5), 2)
        updated_tail = round(tail + delta, 2)
        text = _("tail_growth", tail=updated_tail, rand_num=delta)

    await UserManager.update_tail_stats(
        target_id,
        tail_fluff=updated_tail,
        cooldown_until=int(time.time()) + COOLDOWN_SECONDS,
    )
    await call.message.edit_text(text)
    await call.answer()
