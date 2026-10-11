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


@router.message(Command("image_health"))
@router.message(F.text.regexp(r"(?i)^проверка\s+картинок(?:\s|$)"))
async def image_health_cmd(message: Message):
    """Owner/sudo: probe every image provider and say why generation fails."""
    import asyncio
    import html
    import os

    if not message.from_user:
        return
    if not (is_owner(message.from_user.id) or await UserManager.is_sudo(message.from_user.id)):
        await message.reply("Эта команда доступна только владельцу/sudo.")
        return
    from bot.horde_client import ai_horde
    from bot.image_generation import image_generator
    from bot.perchance_furry import perchance_furry

    waiting = await message.reply("🔎 Проверяю генераторы изображений…")
    providers = os.getenv("IMAGE_PROVIDERS", "horde,perchance,comfyui")
    (horde_ok, horde_msg), (perch_ok, perch_msg), comfy = await asyncio.gather(
        ai_horde.probe(), perchance_furry.probe(), image_generator.healthcheck()
    )
    mark = lambda ok: "✅" if ok else "❌"  # noqa: E731
    comfy_ok = comfy.startswith("OK")
    lines = [
        "🎨 <b>Генераторы изображений</b>",
        f"Порядок: <code>{html.escape(providers)}</code>",
        f"{mark(horde_ok)} AI Horde — {html.escape(horde_msg)}",
        f"{mark(perch_ok)} Perchance — {html.escape(perch_msg)}",
        f"{mark(comfy_ok)} ComfyUI — {html.escape(comfy)}",
    ]
    if not (horde_ok or perch_ok or comfy_ok):
        lines.append("\n⚠️ Ни один не отвечает. Проверь доступ сервера в интернет (curl https://aihorde.net/api/v2/status/heartbeat) и `docker compose logs --tail=80 kira`.")
    elif not horde_ok and not perch_ok:
        lines.append("\nОнлайн-генераторы недоступны; работает только локальный ComfyUI.")
    await waiting.edit_text("\n".join(lines))
