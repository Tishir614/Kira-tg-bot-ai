from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.help_hub import categories, keyboard, render_category, render_main
from bot.help_ui import help_url

router = Router(name="help_hub")


@router.callback_query(F.data.startswith("hub:"))
async def hub_callback(call: CallbackQuery):
    from bot.handlers.commands import cmd_manager  # late import: commands imports the hub

    try:
        _, scope, kind, idx_s, page_s = (call.data or "").split(":")
        idx, page = int(idx_s), int(page_s)
    except ValueError:
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    cats = categories(scope == "a", cmd_manager.commands)
    me = await call.bot.get_me()
    support = f"https://t.me/{me.username}?start=support"
    if kind == "c" and 0 <= idx < len(cats):
        text, pages = render_category(cats, idx, page)
        markup = keyboard(cats, scope, idx=idx, page=page, pages=pages, support_url=support, site_url=help_url() or "")
    else:
        text = render_main(cats)
        markup = keyboard(cats, scope, support_url=support, site_url=help_url() or "")
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # "message is not modified" when the same button is pressed twice
    await call.answer()
