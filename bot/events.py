from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import os


class EventService:
    def __init__(self) -> None:
        self._birthday_seen: set[tuple[int, int, str]] = set()

    @property
    def tz(self) -> ZoneInfo:
        name = os.getenv("BOT_TIMEZONE", "Europe/Vilnius")
        try:
            return ZoneInfo(name)
        except Exception:
            return ZoneInfo("UTC")

    def seasonal_event(self) -> tuple[str, str]:
        now = datetime.now(self.tz)
        md = (now.month, now.day)
        if now.month == 12 and now.day >= 20 or now.month == 1 and now.day <= 8:
            return "🎄 Зимний фестиваль", "За daily и мини-игры действует праздничное настроение."
        if now.month == 10 and now.day >= 20:
            return "🎃 Ночь Kira", "Осенний хоррор-ивент: самое время для RP и мемов."
        if now.month in {6, 7, 8}:
            return "☀️ Летний сезон", "Летний серверный ивент активен."
        if now.month in {3, 4, 5}:
            return "🌸 Весенний сезон", "Весенний серверный ивент активен."
        return "🍂 Осенний сезон", "Осенний серверный ивент активен."

    def should_birthday_announce(self, chat_id: int, user_id: int, day: int | None, month: int | None) -> bool:
        if not day or not month:
            return False
        now = datetime.now(self.tz)
        if (now.day, now.month) != (day, month):
            return False
        key = (chat_id, user_id, now.date().isoformat())
        if key in self._birthday_seen:
            return False
        self._birthday_seen.add(key)
        if len(self._birthday_seen) > 5000:
            self._birthday_seen = {key}
        return True


event_service = EventService()
