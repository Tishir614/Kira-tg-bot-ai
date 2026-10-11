from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.owners import is_owner
from bot.sql import UserManager
from bot.usage_stats import stats

router = Router(name="owner_stats")


@router.message(Command("stats"))
@router.message(F.text.regexp(r"(?i)^статистика(?:\s|$)"))
async def stats_cmd(message: Message):
    if not message.from_user:
        return
    if not (is_owner(message.from_user.id) or await UserManager.is_sudo(message.from_user.id)):
        await message.reply("Эта команда доступна только владельцу/sudo.")
        return
    raw = re.sub(r"(?i)^(?:/stats(?:@\w+)?|статистика)\s*", "", message.text or "").strip().lower()
    days = {"": 1, "день": 1, "сегодня": 1, "неделя": 7, "week": 7, "месяц": 30, "month": 30}.get(raw)
    if days is None:
        await message.reply("Использование: <code>/stats</code>, <code>/stats неделя</code>, <code>/stats месяц</code>")
        return
    stats().flush(force=True)
    await message.reply(stats().render(days))
