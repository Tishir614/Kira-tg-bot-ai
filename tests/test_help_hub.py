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


def test_fursona_flow(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from bot import sql
    from bot.handlers import fursona as fz
    from bot.sql.orm_tables import TableBase

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'f.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(TableBase.metadata.create_all)
        monkeypatch.setattr(sql, "session_factory", async_sessionmaker(engine, expire_on_commit=False))

        def msg(text):
            return SimpleNamespace(text=text, reply=AsyncMock(), from_user=SimpleNamespace(id=7),
                                   chat=SimpleNamespace(id=7, type="private"))

        m = msg("/fursona")
        await fz.fursona_cmd(m)
        assert "Твоя фурсона" in m.reply.await_args.args[0] and "/fursona рыжая" in m.reply.await_args.args[0]
        m = msg("/fursona ребёнок лиса")
        await fz.fursona_cmd(m)
        assert "младше 18" in m.reply.await_args.args[0]
        m = msg("/fursona рыжая лиса, зелёные глаза")
        await fz.fursona_cmd(m)
        assert "сохранена" in m.reply.await_args.args[0]
        m = msg("/fursona")
        await fz.fursona_cmd(m)
        assert "зелёные глаза" in m.reply.await_args.args[0]
        m = msg("/fursona clear")
        await fz.fursona_cmd(m)
        m = msg("/me_image у костра")
        await fz.me_image_cmd(m)
        assert "Сначала опиши" in m.reply.await_args.args[0]
        await engine.dispose()
    asyncio.run(scenario())


def test_image_count_option():
    from bot.image_styles import extract_count
    assert extract_count("лиса, количество:3") == ("лиса", 3)
    assert extract_count("лиса n=99")[1] == 4  # clamped to IMAGE_MAX_VARIANTS
    assert extract_count("лиса") == ("лиса", 1) and extract_count("лиса count:0")[1] == 1


def test_variants_album(monkeypatch):
    from bot.handlers import suite
    from bot.image_generation import GeneratedImage, ExplicitImagePrompt

    async def scenario():
        calls = []

        async def gen(prompt, kira=False, mature=False):
            calls.append(prompt)
            if len(calls) == 2:
                raise RuntimeError("one failed")
            return GeneratedImage(b"IMG", "image/jpeg", "AI Horde (furry)")

        monkeypatch.setattr(suite.image_generator, "generate", gen)
        waiting = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        msg = SimpleNamespace(reply=AsyncMock(return_value=waiting), reply_media_group=AsyncMock(), reply_photo=AsyncMock(),
                              answer=AsyncMock(), from_user=SimpleNamespace(id=5))
        await suite._image_variants_impl(msg, "лиса количество:3", "лиса", 3, kira=False)
        assert len(calls) == 3 and all(c == "лиса" for c in calls)
        media = msg.reply_media_group.await_args.args[0]
        assert len(media) == 2 and "2 из 3" in media[0].caption and media[1].caption is None
        assert msg.answer.await_args.kwargs["reply_markup"].inline_keyboard

        async def blocked(prompt, kira=False, mature=False):
            raise ExplicitImagePrompt("нельзя")
        monkeypatch.setattr(suite.image_generator, "generate", blocked)
        waiting2 = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        msg2 = SimpleNamespace(reply=AsyncMock(return_value=waiting2), from_user=SimpleNamespace(id=5))
        await suite._image_variants_impl(msg2, "x", "x", 2, kira=False)
        assert "нельзя" in waiting2.edit_text.await_args.args[0]
    asyncio.run(scenario())
