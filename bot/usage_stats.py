"""Owner usage statistics: per-day counters persisted to a small JSON file (no DB migration).

Privacy: only counts are stored; user and chat ids are kept as a salted-hash count of distinct
values per day, never as readable ids, and message text is never stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

KEEP_DAYS = 31
FLUSH_EVERY = 60.0
_LAT_KEEP = 300


def _today() -> str:
    return date.today().isoformat()


class UsageStats:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from bot.config import settings

            path = Path(settings.data_dir) / "usage_stats.json"
        self.path = path
        self.salt = os.getenv("USAGE_SALT", "kira")
        self.days: dict[str, dict[str, Any]] = {}
        self._last_flush = 0.0
        self._load()

    # ---- persistence ----
    def _load(self) -> None:
        try:
            self.days = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
            if not isinstance(self.days, dict):
                self.days = {}
        except Exception:
            self.days = {}

    def flush(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < FLUSH_EVERY:
            return
        self._last_flush = now
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        self.days = {d: v for d, v in self.days.items() if d >= cutoff}
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.days, ensure_ascii=False), "utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    # ---- recording ----
    def _day(self) -> dict[str, Any]:
        return self.days.setdefault(_today(), {
            "counters": {}, "users": [], "chats": [], "lat": [], "lat_sum": 0.0, "lat_n": 0, "lat_max": 0.0,
        })

    def _hash(self, value: int) -> str:
        return hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:12]

    def count(self, key: str, n: int = 1) -> None:
        counters = self._day()["counters"]
        counters[key] = counters.get(key, 0) + n
        self.flush()

    def seen(self, user_id: int | None, chat_id: int | None) -> None:
        day = self._day()
        for field, value in (("users", user_id), ("chats", chat_id)):
            if value:
                h = self._hash(int(value))
                if h not in day[field]:
                    day[field].append(h)

    def latency(self, seconds: float) -> None:
        day = self._day()
        day["lat"] = (day["lat"] + [round(seconds, 2)])[-_LAT_KEEP:]
        day["lat_sum"] += seconds
        day["lat_n"] += 1
        day["lat_max"] = max(day["lat_max"], seconds)
        self.flush()

    # ---- reporting ----
    def report(self, days: int = 1) -> dict[str, Any]:
        wanted = [(date.today() - timedelta(days=i)).isoformat() for i in range(days)]
        counters: Counter = Counter()
        users: set[str] = set()
        chats: set[str] = set()
        lat: list[float] = []
        lat_sum = lat_n = 0
        lat_max = 0.0
        for d in wanted:
            row = self.days.get(d)
            if not row:
                continue
            counters.update(row["counters"])
            users.update(row["users"])
            chats.update(row["chats"])
            lat += row["lat"]
            lat_sum += row["lat_sum"]
            lat_n += row["lat_n"]
            lat_max = max(lat_max, row["lat_max"])
        lat.sort()
        return {
            "counters": counters, "users": len(users), "chats": len(chats),
            "lat_avg": (lat_sum / lat_n) if lat_n else 0.0,
            "lat_p95": lat[int(len(lat) * 0.95) - 1] if len(lat) >= 5 else (lat[-1] if lat else 0.0),
            "lat_max": lat_max, "lat_n": lat_n,
        }

    def render(self, days: int = 1) -> str:
        r = self.report(days)
        c = r["counters"]
        cmds = sorted(((k[4:], v) for k, v in c.items() if k.startswith("cmd:")), key=lambda x: -x[1])[:10]
        providers = sorted(((k[4:], v) for k, v in c.items() if k.startswith("img:")), key=lambda x: -x[1])
        title = "сегодня" if days == 1 else f"за {days} дн."
        lines = [
            f"📊 <b>Статистика {title}</b>",
            f"Активных пользователей: <b>{r['users']}</b> · чатов: <b>{r['chats']}</b>",
            f"Сообщений: {c.get('messages', 0)} · команд: {c.get('commands', 0)}",
            f"AI: ✅ {c.get('ai_ok', 0)} · ❌ {c.get('ai_fail', 0)} · RP-ходов: {c.get('rp_turns', 0)}",
        ]
        if r["lat_n"]:
            lines.append(f"Время ответа AI: ср. {r['lat_avg']:.1f} c · p95 {r['lat_p95']:.1f} c · макс {r['lat_max']:.1f} c")
        modes = sorted(((k[5:], v) for k, v in c.items() if k.startswith("mode:")), key=lambda x: -x[1])
        if modes:
            lines.append("Режимы: " + ", ".join(f"{m} {n}" for m, n in modes))
        if providers:
            lines.append("Картинки: " + ", ".join(f"{p} {n}" for p, n in providers))
        if cmds:
            lines.append("Топ команд: " + ", ".join(f"/{n} {v}" for n, v in cmds))
        return "\n".join(lines)


_instance: UsageStats | None = None


def stats() -> UsageStats:
    global _instance
    if _instance is None:
        _instance = UsageStats()
    return _instance


def safe(fn_name: str, *args, **kwargs) -> None:
    """Statistics must never break a request."""
    try:
        getattr(stats(), fn_name)(*args, **kwargs)
    except Exception:
        pass
