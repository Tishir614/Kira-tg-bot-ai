import os

os.environ.setdefault("TOKEN", "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("OWNER_ID", "1")
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import help_hub as hh
from bot.handlers import commands as c  # imported at collection time: pyrogram needs an event loop
from bot.handlers.help_hub import hub_callback


class Cmd(SimpleNamespace):
    pass


LEGACY = {"+рп": Cmd(description="добавить RP <b>", admin_only=True), "баланс": Cmd(description="деньги", admin_only=False)}


def test_every_page_fits_telegram_and_buttons_are_valid():
    for admin in (False, True):
        cats = hh.categories(admin, LEGACY)
        assert len(cats) >= 11
        assert len(hh.render_main(cats)) < 4000
        kb = hh.keyboard(cats, "a" if admin else "u")
        for i in range(len(cats)):
            text, pages = hh.render_category(cats, i, 0)
            assert len(text) < 4096, cats[i][0]
            for p in range(pages):
                t, _ = hh.render_category(cats, i, p)
                assert len(t) < 4096
                for row in hh.keyboard(cats, "a", idx=i, page=p, pages=pages).inline_keyboard:
                    for b in row:
                        assert len(b.callback_data or "x") <= 64
        assert all(len(b.callback_data) <= 64 for r in kb.inline_keyboard for b in r)


def test_new_commands_are_listed_and_admin_split():
    user = " ".join(" ".join(l) for _, l in hh.categories(False, LEGACY))
    admin = " ".join(" ".join(l) for _, l in hh.categories(True, LEGACY))
    for cmd in ("/rp", "/persona", "/styles", "/forget", "/memory", "/image"):
        assert cmd in user or hh.russian_usage(cmd) in user, cmd
    assert "+рп" not in user and "+рп" in admin
    assert "&lt;b&gt;" in admin  # descriptions are HTML-escaped


def test_pagination_and_send_help():
    pages = hh.paginate([f"line {i} " + "x" * 200 for i in range(40)], 3000)
    assert len(pages) > 1 and all(sum(len(l) + 1 for l in p) <= 3000 for p in pages)

    async def scenario():
        reply = AsyncMock()
        msg = SimpleNamespace(reply=reply, bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="kira_bot"))),
                              from_user=SimpleNamespace(id=5), chat=SimpleNamespace(type="private", id=5))
        await c._send_help(msg, admin=False)
        text = reply.await_args.args[0]
        assert "Центр помощи" in text and "Всего команд" in text
        assert reply.await_args.kwargs["reply_markup"].inline_keyboard
    asyncio.run(scenario())


def test_callback_edits_message_in_place():
    async def scenario():
        edit = AsyncMock()
        call = SimpleNamespace(data="hub:u:c:0:0", message=SimpleNamespace(edit_text=edit), answer=AsyncMock(),
                               bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="kira_bot"))))
        await hub_callback(call)
        assert "AI и общение" in edit.await_args.args[0] and "🏠 Меню" in str(edit.await_args.kwargs["reply_markup"])
        call.data = "hub:u:m:0:0"
        await hub_callback(call)
        assert "Центр помощи" in edit.await_args.args[0]
        call.data = "hub:garbage"
        await hub_callback(call)  # must not raise
    asyncio.run(scenario())
