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

    async def fake(prompt, negative="", size=None):
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


def test_image_buttons():
    from bot import image_buttons as ib
    t = ib.remember(7, "лиса, стиль:аниме", False)
    assert ib.lookup(t).user_id == 7 and ib.lookup("nope") is None
    assert ib.strip_style("лиса, стиль:аниме") == "лиса"
    kb = ib.keyboard(t)
    assert all(len(b.callback_data) <= 64 for b in kb.inline_keyboard[0])
    for i in range(400):
        ib.remember(1, "x", False)
    assert ib.lookup(t) is None  # LRU bounded


def test_furry_prompt_compose():
    from bot.furry_prompt import compose
    pos, neg = compose("anthro fox, female, nude, beach")
    assert pos.startswith("solo") and "rating_explicit" in pos and "masterpiece" in pos
    assert pos.lower().count("anthro") == 1 and "censored" in neg and "child" in neg
    pos, neg = compose("wolf and fox duo, forest")
    assert "solo" not in pos and "rating_safe" in pos and "censored" not in neg
    assert "rating_questionable" in compose("fox in bikini")[0]
    pos, _ = compose("sitting by window", kira_visual="Kira visual")
    assert "Kira visual" in pos and "anthro furry" not in pos


def test_rp_director_inserts():
    assert "поворот" in rp_engine.twist_prompt() and "не делай ничего за персонажа" in rp_engine.NEXT_PROMPT
    assert rp_engine.twist_prompt().count("[Режиссёрская вставка]") == 1


def test_image_format_option_and_size_passthrough(monkeypatch):
    from bot.image_styles import extract_format, FORMATS
    assert extract_format("лиса, формат:портрет") == ("лиса", "portrait")
    assert extract_format("лиса формат:широкий")[1] == "wide" and extract_format("лиса")[1] is None
    assert extract_format("лиса формат:abc")[1] is None
    seen = {}

    async def fake(prompt, negative="", size=None):
        seen["size"] = size
        return b"img", "image/jpeg"

    monkeypatch.setattr(ig.perchance_furry, "generate", fake)
    monkeypatch.setenv("IMAGE_PROVIDERS", "perchance")
    monkeypatch.setattr("bot.ai_client.ai", type("A", (), {"enabled": False})())
    asyncio.run(ImageGenerator().generate("лиса на пляже формат:широкий"))
    assert seen["size"] == FORMATS["wide"] == (768, 512)


def test_horde_uses_requested_size():
    from bot import horde_client as hc
    p = hc.build_payload("fox", "", ["Furry Epoch"], 768, 512, 28, 7)
    assert (p["params"]["width"], p["params"]["height"]) == (768, 512)


def test_horde_falls_back_to_general_models_and_reports_label(monkeypatch):
    from bot import horde_client as hc
    live = [{"name": "Deliberate", "count": 2}, {"name": "Furry Epoch", "count": 0}]
    assert hc.pick_models(live, ["Furry Epoch", "Fluffyrock"]) == []
    assert hc.pick_models(live, hc.DEFAULT_FALLBACK.split(","), hints=False) == ["Deliberate"]

    class Resp:
        def __init__(self, data=None, raw=b""):
            self._d, self._raw, self.status, self.headers = data, raw, 200, {"Content-Type": "image/webp"}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def text(self): return str(self._d)
        async def json(self, content_type=None): return self._d
        async def read(self): return self._raw

    class Session:
        def request(self, method, url, **kw):
            if url.endswith("/status/models"): return Resp(live)
            if url.endswith("/generate/async"):
                assert kw["json"]["models"] == ["Deliberate"]
                return Resp({"id": "J"})
            if "/generate/check/" in url: return Resp({"done": True})
            return Resp({"generations": [{"img": "https://r2/x.webp", "censored": False}]})
        def get(self, url, **kw): return Resp(raw=b"IMG")

    async def fake_get(): return Session()
    monkeypatch.setattr(hc.http_client, "get", fake_get)
    horde = hc.AIHorde()
    assert asyncio.run(horde.generate("anthro fox"))[0] == b"IMG" and horde.last_models == ["Deliberate"]
    ok, msg = asyncio.run(horde.probe())
    assert ok and "запасные: Deliberate" in msg


def test_all_providers_failing_explains_why(monkeypatch):
    async def horde_fail(*a, **k):
        raise ig.HordeError("в AI Horde сейчас нет активных фурри-моделей")

    async def perch_fail(*a, **k):
        raise ig.PerchanceError("Perchance недоступен: timeout")

    monkeypatch.setattr(ig.ai_horde, "generate", horde_fail)
    monkeypatch.setattr(ig.perchance_furry, "generate", perch_fail)
    monkeypatch.setattr("bot.ai_client.ai", type("A", (), {"enabled": False})())
    gen = ImageGenerator()
    gen.base_url = "http://127.0.0.1:9"  # nothing listens there
    import pytest as _pytest
    with _pytest.raises(ig.ImageGenerationError) as err:
        asyncio.run(gen.generate("лиса на пляже"))
    text = str(err.value)
    assert "AI Horde:" in text and "нет активных фурри-моделей" in text
    assert "Perchance:" in text and "ComfyUI:" in text


def test_probe_never_raises(monkeypatch):
    from bot import horde_client as hc
    from bot import perchance_furry as pf

    async def boom():
        raise RuntimeError("no network")
    monkeypatch.setattr(hc.http_client, "get", boom)
    monkeypatch.setattr(pf.http_client, "get", boom)
    ok, msg = asyncio.run(hc.AIHorde().probe())
    assert not ok and "недоступен" in msg
    ok, msg = asyncio.run(pf.PerchanceFurry().probe())
    assert not ok and "недоступен" in msg
