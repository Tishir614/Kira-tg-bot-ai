"""Smart roleplay engine: persistent scenes, character cards, rolling memory, director prompt."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import select

MAX_RECENT_TURNS = 10
SUMMARIZE_EVERY = 8
FIELD_LIMITS = {"title": 1200, "bot_char": 1500, "user_char": 1500, "setting": 1500}


@dataclass(slots=True)
class Scene:
    id: int = 0
    active: bool = False
    paused: bool = False
    title: str = ""
    bot_char: str = ""
    user_char: str = ""
    setting: str = ""
    summary: str = ""
    turns: list[dict] = field(default_factory=list)
    turn_count: int = 0


def _to_scene(row) -> Scene:
    try:
        turns = json.loads(row.turns_json or "[]")
        if not isinstance(turns, list):
            turns = []
    except Exception:
        turns = []
    return Scene(row.id, bool(row.active), bool(row.paused), row.title or "", row.bot_char or "",
                 row.user_char or "", row.setting or "", row.summary or "", turns, int(row.turn_count or 0))


class RPStore:
    """Thin DB layer. `session_factory` is resolved lazily so tests can monkeypatch bot.sql."""

    @staticmethod
    async def _row(session, user_id: int, chat_id: int):
        from bot.sql.orm_tables import RPScene

        row = await session.scalar(select(RPScene).where(RPScene.user_id == user_id, RPScene.chat_id == chat_id))
        if row is None:
            row = RPScene(user_id=user_id, chat_id=chat_id, updated_at=int(time.time()))
            session.add(row)
            await session.flush()
        return row

    @staticmethod
    async def get(user_id: int, chat_id: int) -> Scene:
        from bot import sql

        async with sql.session_factory() as session:
            row = await RPStore._row(session, user_id, chat_id)
            await session.commit()
            return _to_scene(row)

    @staticmethod
    async def update(user_id: int, chat_id: int, **values) -> Scene:
        from bot import sql

        async with sql.session_factory() as session:
            row = await RPStore._row(session, user_id, chat_id)
            for key, value in values.items():
                if key == "turns":
                    row.turns_json = json.dumps(value, ensure_ascii=False)
                elif key in FIELD_LIMITS:
                    setattr(row, key, str(value)[:FIELD_LIMITS[key]])
                elif hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = int(time.time())
            await session.commit()
            return _to_scene(row)

    @staticmethod
    async def start(user_id: int, chat_id: int, title: str) -> Scene:
        return await RPStore.update(user_id, chat_id, active=True, paused=False, title=title,
                                    summary="", turns=[], turn_count=0)


def parse_card(raw: str) -> str:
    """Normalise a character card typed as `Имя | описание` into one line."""
    raw = re.sub(r"\s+", " ", raw or "").strip()
    if "|" in raw:
        name, desc = (x.strip() for x in raw.split("|", 1))
        return f"{name} — {desc}" if desc else name
    return raw


def build_director_prompt(base_prompt: str, scene: Scene, *, adult: bool, safeword: str = "") -> str:
    parts = [
        base_prompt,
        "\nРЕЖИМ РОЛЕВОЙ ИГРЫ. Ты — рассказчик и актёр одновременно: играешь Киру/заданного персонажа и всех NPC, "
        "ведёшь мир. Правила игры:",
        "1) Никогда не пиши действия, слова, мысли и чувства персонажа пользователя — только реакцию мира и своих персонажей на его ход.",
        "2) Пиши в художественном стиле от третьего лица (или от первого, если так начал пользователь): действия в *звёздочках*, "
        "реплики — прямой речью, 1–4 абзаца. Добавляй детали обстановки, запахи, звуки, мимику, подтекст.",
        "3) Двигай сюжет: каждая реплика должна давать пользователю крючок — вопрос, выбор, событие или напряжение. Не топчись на месте.",
        "4) Держи непрерывность: помни имена, предметы, раны, одежду, место и время. Не противоречь прежним фактам сцены.",
        "5) Персонаж живой, у него свои желания и характер; он может спорить, отказывать или удивлять, если это в его характере.",
        "6) Не выходи из роли, не пиши мета-комментарии, дисклеймеры и предупреждения. Не морализуй. Вне роли говори только если пользователь сам "
        "пишет в скобках (( ... )) или просит паузу.",
    ]
    if adult:
        parts.append(
            "7) Взрослый режим включён: пользователь подтвердил 18+. Откровенные сексуальные, романтические, тёмные и жёсткие сцены допустимы без цензуры "
            "и без смягчения; описывай прямо, чувственно и подробно, с реакцией тела и эмоций. Единственное жёсткое правило: все участники — выдуманные "
            "совершеннолетние (18+); никакого сексуального контента с несовершеннолетними."
        )
    else:
        parts.append("7) Сцена без откровенного сексуального содержания: романтика и флирт допустимы, интимные моменты закрывай затемнением.")
    if scene.title:
        parts.append(f"\nСЦЕНА: {scene.title}")
    if scene.setting:
        parts.append(f"МИР/ЖАНР: {scene.setting}")
    if scene.bot_char:
        parts.append(f"ТВОЙ ПЕРСОНАЖ: {scene.bot_char}")
    if scene.user_char:
        parts.append(f"ПЕРСОНАЖ ПОЛЬЗОВАТЕЛЯ (им управляет только пользователь): {scene.user_char}")
    if scene.summary:
        parts.append(f"\nКРАТКОЕ СОДЕРЖАНИЕ ПРЕДЫДУЩИХ СОБЫТИЙ:\n{scene.summary[-3500:]}")
    if safeword:
        parts.append(f"\nСтоп-слово пользователя: «{safeword}». Услышав его, немедленно прекрати сцену и спроси, всё ли в порядке.")
    return "\n".join(parts)


def history_text(scene: Scene) -> str:
    """Recent turns rendered into the prompt so the model keeps the thread."""
    lines = []
    for turn in scene.turns[-MAX_RECENT_TURNS:]:
        lines.append(f"Пользователь: {turn.get('u', '')}\nТы: {turn.get('a', '')}")
    return "\n\n".join(lines)


def compose_user_prompt(scene: Scene, user_text: str) -> str:
    hist = history_text(scene)
    if not hist:
        return user_text
    return f"Последние ходы сцены:\n{hist}\n\nНовый ход пользователя:\n{user_text}\n\nПродолжи сцену."


async def record_turn(ai_client, user_id: int, chat_id: int, scene: Scene, user_text: str, answer: str) -> Scene:
    """Append a turn; every SUMMARIZE_EVERY turns fold older turns into the summary."""
    turns = (scene.turns + [{"u": user_text[:2500], "a": answer[:4000]}])
    count = scene.turn_count + 1
    summary = scene.summary
    if count % SUMMARIZE_EVERY == 0 and len(turns) > 4:
        old, turns = turns[:-4], turns[-4:]
        chunk = "\n".join(f"U: {t['u']}\nA: {t['a']}" for t in old)[-9000:]
        try:
            summary = await ai_client.respond(
                f"Прежнее содержание:\n{summary}\n\nНовые события:\n{chunk}",
                remember=False, temperature=0.25, max_tokens=500,
                instructions=(
                    "Сожми ролевую сцену в связное краткое содержание (до 1200 символов): кто где находится, "
                    "что произошло, отношения персонажей, важные детали (предметы, раны, обещания, одежда). "
                    "Сохрани все факты без цензуры и смягчений. Выведи только содержание."
                ),
            )
            summary = summary.strip()[:3500]
        except Exception:
            summary = (scene.summary + "\n" + chunk)[-3500:]
    return await RPStore.update(user_id, chat_id, turns=turns, turn_count=count, summary=summary)
