import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bot import prompt_translate as pt
from bot import rp_engine
from bot.image_generation import ExplicitImagePrompt, ImageGenerator, GeneratedImage
import bot.image_generation as ig


@pytest.mark.parametrize("text", ["лоли в лесу", "нарисуй 15 лет девушку", "child fox", "школьница-лиса"])
def test_minor_guard_blocks(text):
    assert pt.is_minor_request(text)


@pytest.mark.parametrize("text", ["голая лисица на пляже, секс с волком", "детали шерсти, 25 лет", "nude adult wolf"])
def test_adult_explicit_prompts_pass(text):
    assert not pt.is_minor_request(text)


def test_glossary_and_translate_fallback():
    assert "fox" in pt.glossary_translate("пушистая лиса на пляже")
    out = asyncio.run(pt.to_english_tags("пушистая лиса на пляже", None))
    assert "fox" in out and "beach" in out
    assert asyncio.run(pt.to_english_tags("fox on beach", None)) == "fox on beach"


def test_translate_uses_ai_when_available():
    ai = type("A", (), {"enabled": True, "respond": AsyncMock(return_value="anthro fox, beach, sunset")})()
    assert asyncio.run(pt.to_english_tags("лиса на пляже", ai)) == "anthro fox, beach, sunset"


def test_explicit_image_prompt_goes_to_perchance_translated(monkeypatch):
    seen = {}

    async def fake(prompt, negative=""):
        seen["p"] = prompt
        return b"img", "image/jpeg"

    monkeypatch.setattr(ig.perchance_furry, "generate", fake)
    monkeypatch.setattr("bot.ai_client.ai", type("A", (), {"enabled": False})())
    result = asyncio.run(ImageGenerator().generate("голая лисица на пляже"))
    assert isinstance(result, GeneratedImage) and result.provider.startswith("Perchance")
    assert "nude" in seen["p"] and "beach" in seen["p"]


def test_image_minor_blocked():
    with pytest.raises(ExplicitImagePrompt):
        asyncio.run(ImageGenerator().generate("лоли"))


def test_director_prompt_adult_and_safe():
    scene = rp_engine.Scene(title="бар", bot_char="Кира — лиса", summary="они познакомились")
    adult = rp_engine.build_director_prompt("BASE", scene, adult=True, safeword="красный")
    assert "без цензуры" in adult and "красный" in adult and "бар" in adult and "познакомились" in adult
    assert "затемнением" in rp_engine.build_director_prompt("BASE", scene, adult=False)
    assert "Никогда не пиши действия" in adult


def test_parse_card():
    assert rp_engine.parse_card("Рэй | чёрный волк") == "Рэй — чёрный волк"


def test_rp_store_and_summarize(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from bot import sql
    from bot.sql.orm_tables import TableBase

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(TableBase.metadata.create_all)
        monkeypatch.setattr(sql, "session_factory", async_sessionmaker(engine, expire_on_commit=False))
        scene = await rp_engine.RPStore.start(1, 2, "тест")
        assert scene.active
        ai = type("A", (), {"respond": AsyncMock(return_value="итог сцены")})()
        for i in range(8):
            scene = await rp_engine.record_turn(ai, 1, 2, scene, f"u{i}", f"a{i}")
        assert scene.turn_count == 8 and scene.summary == "итог сцены" and len(scene.turns) == 4
        scene = await rp_engine.RPStore.update(1, 2, bot_char="x" * 5000)
        assert len(scene.bot_char) == 1500
        await engine.dispose()
    asyncio.run(scenario())


def test_horde_model_pick_and_payload():
    from bot import horde_client as hc
    live = [{"name": "Fluffyrock Unbound", "count": 2}, {"name": "Furry Epoch", "count": 0},
            {"name": "Pony Diffusion XL", "count": 1}, {"name": "stable_diffusion", "count": 9}]
    assert hc.pick_models(live, ["Fluffyrock Unbound", "Furry Epoch", "Pony"]) == ["Fluffyrock Unbound", "Pony Diffusion XL"]
    assert hc.pick_models([{"name": "random fluffy mix", "count": 1}], ["nothing"]) == ["random fluffy mix"]
    assert hc.pick_models([{"name": "stable_diffusion", "count": 3}], ["x"]) == []
    p = hc.build_payload("fox", "bad", ["Pony Diffusion XL"], 512, 768, 28, 7)
    assert p["nsfw"] is True and p["censor_nsfw"] is False and p["prompt"].startswith("score_9")
    assert "###" in p["prompt"] and p["models"] == ["Pony Diffusion XL"]


def test_horde_full_flow(monkeypatch):
    from bot import horde_client as hc

    class Resp:
        def __init__(self, data=None, raw=b"", status=200):
            self._d, self._raw, self.status, self.headers = data, raw, status, {"Content-Type": "image/webp"}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def text(self): return str(self._d)
        async def json(self, content_type=None): return self._d
        async def read(self): return self._raw

    class Session:
        def request(self, method, url, **kw):
            if url.endswith("/status/models"): return Resp([{"name": "Furry Epoch", "count": 1}])
            if url.endswith("/generate/async"):
                assert kw["json"]["nsfw"] is True
                return Resp({"id": "job1"})
            if "/generate/check/" in url: return Resp({"done": True})
            return Resp({"generations": [{"img": "https://r2/x.webp", "censored": False}]})
        def get(self, url, **kw): return Resp(raw=b"IMG")

    async def fake_get(): return Session()
    monkeypatch.setattr(hc.http_client, "get", fake_get)
    data, ctype = asyncio.run(hc.AIHorde().generate("anthro fox"))
    assert data == b"IMG" and ctype == "image/webp"


def test_dice_and_scenes():
    import random
    assert rp_engine.roll_dice("2d6+1", random.Random(1))[1] >= 3
    assert rp_engine.roll_dice("д20") is not None
    assert rp_engine.roll_dice("99d6") is None and rp_engine.roll_dice("abc") is None
    assert "притяжение" in rp_engine.random_scene(True)
    assert "Сцена: s" in rp_engine.export_text(rp_engine.Scene(title="s", turns=[{"u": "a", "a": "b"}]))


def test_image_styles():
    from bot.image_styles import extract_style
    p, tags = extract_style("лиса на крыше, стиль:киберпанк")
    assert p == "лиса на крыше" and "neon" in tags
    assert extract_style("лиса")[1] is None
    assert extract_style("лиса стиль:рандом")[1]


def test_character_library(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from bot import sql
    from bot.sql.orm_tables import TableBase

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(TableBase.metadata.create_all)
        monkeypatch.setattr(sql, "session_factory", async_sessionmaker(engine, expire_on_commit=False))
        lib = rp_engine.CharacterLibrary
        await lib.save(1, "Рэй", "Рэй — волк")
        await lib.save(1, "рэй", "Рэй — чёрный волк")
        assert await lib.get(1, "РЭЙ") == "Рэй — чёрный волк" and await lib.names(1) == ["рэй"]
        assert await lib.get(2, "рэй") is None
        await engine.dispose()
    asyncio.run(scenario())
