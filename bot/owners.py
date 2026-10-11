"""Stable Telegram ID bindings for the three Kira owners.

The primary owner comes from OWNER_ID. Secondary slots are bound by the primary owner using numeric Telegram IDs.
Usernames are never used for authorization.
"""
from __future__ import annotations

import asyncio
import json
import os

from bot.config import settings

SLOTS = {2: "tishir22", 3: "helis_pro1"}
_lock = asyncio.Lock()


def _path():
    return settings.data_dir / "owners.json"


def _bindings() -> dict[str, int]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data.items() if str(k) in {"2", "3"} and int(v) > 0}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def owner_ids() -> set[int]:
    ids = {settings.owner_id} if settings.owner_id else set()
    ids.update(_bindings().values())
    for key in ("SECOND_OWNER_ID", "THIRD_OWNER_ID"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit() and int(raw) > 0:
            ids.add(int(raw))
    return ids


def is_owner(user_id: int | None) -> bool:
    return bool(user_id and user_id in owner_ids())


async def bind_owner(slot: int, user_id: int, *, primary: bool = False) -> str:
    if slot not in SLOTS or user_id <= 0:
        return "Нужен слот 2 или 3 и положительный Telegram ID."
    if not primary:
        return "Назначить владельца может только главный владелец."
    async with _lock:
        bindings = _bindings()
        if user_id in (value for key, value in bindings.items() if key != str(slot)):
            return "Этот Telegram ID уже занимает другой слот."
        bindings[str(slot)] = user_id
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(bindings, ensure_ascii=False), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    return f"✅ Владелец №{slot} закреплён за Telegram ID {user_id}."
