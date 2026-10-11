from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers.commands import cmd_manager
from bot.sql import EconomyManager

router = Router(name="kira-world-2.0")
_LOCK = asyncio.Lock()
_DATA = Path(os.getenv("DATA_DIR", "/app/static")) / "kira_world.json"

MOODS = {
    "happy": "😸 довольная",
    "cozy": "☕ уютная",
    "curious": "🦊 любопытная",
    "sleepy": "🌙 сонная",
    "hyped": "⚡ заряженная",
}
BOSSES = [
    ("👾 Багожор", 180),
    ("🦠 Лагус Максимус", 240),
    ("📵 Пожиратель пинга", 300),
    ("🗃 Архивный мимик", 220),
]


def _default() -> dict:
    return {"mood": "curious", "energy": 75, "affection": 0, "activity": "читает беседу", "boss": None, "quest": None, "updated": int(time.time())}


def _read_all() -> dict:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_all(data: dict) -> None:
    _DATA.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _DATA)


def _decay(s: dict) -> None:
    now = int(time.time())
    elapsed = max(0, now - int(s.get("updated", now)))
    if elapsed >= 3600:
        s["energy"] = max(10, int(s.get("energy", 75)) - min(25, elapsed // 3600))
    s["updated"] = now


async def _state(chat_id: int) -> tuple[dict, dict]:
    data = _read_all()
    key = str(chat_id)
    s = data.setdefault(key, _default())
    _decay(s)
    return data, s


@cmd_manager.register("мир киры", "Живое состояние Киры и событие беседы.")
@router.message(Command("kira_world"))
@router.message(F.text.lower().in_({"мир киры", "кира мир", "состояние киры"}))
async def world(message: Message) -> None:
    async with _LOCK:
        data, s = await _state(message.chat.id)
        _write_all(data)
    boss = s.get("boss")
    boss_line = "нет"
    if boss:
        boss_line = f"{boss['name']} · ❤️ {boss['hp']}/{boss['max_hp']}"
    quest = s.get("quest") or "сейчас тихо"
    await message.reply(
        "🌌 <b>Мир Киры 2.0</b>\n"
        f"Кира: <b>{MOODS.get(s.get('mood'), '🦊 обычная')}</b>\n"
        f"Энергия: <b>{s.get('energy', 0)}%</b>\n"
        f"Теплота беседы: <b>{s.get('affection', 0)}</b> ❤️\n"
        f"Занятие: <b>{s.get('activity', 'читает чат')}</b>\n"
        f"Событие: <b>{quest}</b>\n"
        f"Босс: <b>{boss_line}</b>"
    )


@router.message(Command("pet"))
@router.message(F.text.lower().in_({"погладить киру", "кира погладить", "погладить"}))
async def pet(message: Message) -> None:
    if not message.from_user:
        return
    async with _LOCK:
        data, s = await _state(message.chat.id)
        s["affection"] = min(9999, int(s.get("affection", 0)) + random.randint(1, 3))
        s["energy"] = min(100, int(s.get("energy", 75)) + 2)
        s["mood"] = random.choice(["happy", "cozy", "curious"])
        s["activity"] = "довольно машет хвостом"
        _write_all(data)
    await EconomyManager.add_xp(message.from_user.id, 2)
    await message.reply(random.choice([
        "🦊 Кира довольно прищурилась. Хвост официально распушён.",
        "✨ +немного лисьего доверия. Кира сделала вид, что это совершенно нормально.",
        "☕ Кира устроилась поудобнее. Кажется, беседа стала чуть уютнее.",
    ]))


@router.message(Command("quest"))
@router.message(F.text.lower().in_({"событие киры", "квест киры", "кира событие"}))
async def quest(message: Message) -> None:
    if not message.from_user:
        return
    async with _LOCK:
        data, s = await _state(message.chat.id)
        if s.get("quest"):
            text = f"🎲 Текущее событие: <b>{s['quest']}</b>"
        else:
            q = random.choice([
                "Эмодзи-охота: отправьте в чат 🦊",
                "Час мемов: Кира собирает самые странные сообщения",
                "Лисий уют: погладьте Киру командой «погладить»",
                "Баговая тревога: вызовите /boss и отбейте атаку",
            ])
            s["quest"] = q
            s["mood"] = "hyped"
            s["energy"] = min(100, int(s.get("energy", 75)) + 8)
            _write_all(data)
            text = f"🎲 <b>Новое событие беседы!</b>\n{q}"
    await message.reply(text)


@router.message(Command("boss"))
@router.message(F.text.lower().in_({"босс", "босс киры", "атаковать босса"}))
async def boss(message: Message) -> None:
    if not message.from_user:
        return
    async with _LOCK:
        data, s = await _state(message.chat.id)
        b = s.get("boss")
        if not b:
            name, hp = random.choice(BOSSES)
            b = {"name": name, "hp": hp, "max_hp": hp, "started": int(time.time())}
            s["boss"] = b
            _write_all(data)
            await message.reply(f"🚨 <b>{name}</b> ворвался в беседу!\n❤️ HP: <b>{hp}</b>\nПишите <code>атаковать босса</code>.")
            return
        dmg = random.randint(8, 28)
        crit = random.random() < 0.12
        if crit:
            dmg *= 2
        b["hp"] = max(0, int(b["hp"]) - dmg)
        if b["hp"] <= 0:
            s["boss"] = None
            s["quest"] = None
            s["affection"] = min(9999, int(s.get("affection", 0)) + 10)
            s["mood"] = "happy"
            _write_all(data)
            await EconomyManager.add_coins(message.from_user.id, 125)
            await EconomyManager.add_xp(message.from_user.id, 30)
            await message.reply(f"💥 <b>{b['name']} побеждён!</b>\nФинальный удар: <b>{dmg}</b>{' 💫 КРИТ' if crit else ''}\nНаграда: <b>125 🪙 + 30 XP</b>.")
            return
        _write_all(data)
    await EconomyManager.add_xp(message.from_user.id, 3)
    await message.reply(f"⚔️ Урон: <b>{dmg}</b>{' 💫 КРИТ' if crit else ''}\n{b['name']}: ❤️ <b>{b['hp']}/{b['max_hp']}</b>")
