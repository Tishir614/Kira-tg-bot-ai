from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import time
import traceback
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from aiogram import Bot
from sqlalchemy import select

from bot import log
from bot.config import settings
from bot.redaction import redact
from bot.sql import database_maintenance, session_factory
from bot.sql.orm_tables import RecoveryIncident


class RecoveryRuntime:
    """Conservative self-healing for transient failures and crash loops.

    Kira never rewrites Python source at runtime. Recovery is limited to safe actions:
    SQLite maintenance, controlled process restart (Docker brings it back), persistent
    incident journaling and owner notifications.
    """

    STATE_FILE = settings.data_dir / ".recovery_state.json"
    RESTART_WINDOW = 15 * 60
    MAX_RESTARTS_PER_WINDOW = 2
    REPEAT_WINDOW = 5 * 60
    REPEAT_THRESHOLD = 3

    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._session_id = uuid.uuid4().hex[:12]
        self._errors: dict[str, deque[float]] = defaultdict(deque)
        self._restart_task: asyncio.Task | None = None
        self._started = False

    @staticmethod
    def _now() -> int:
        return int(time.time())

    @classmethod
    def _load_state(cls) -> dict[str, Any]:
        try:
            data = json.loads(cls.STATE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _save_state(cls, state: dict[str, Any]) -> None:
        cls.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = cls.STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(cls.STATE_FILE)

    @staticmethod
    def fingerprint(exc: BaseException) -> str:
        raw = f"{type(exc).__module__}.{type(exc).__name__}:{str(exc)[:300]}"
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]

    @staticmethod
    def classify(exc: BaseException) -> str:
        text = f"{type(exc).__name__}: {exc}".casefold()
        if "database is locked" in text or "sqlite" in text or "operationalerror" in text:
            return "database"
        if "redis" in text or "connectionerror" in text or "connection refused" in text:
            return "connection"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "not json serializable" in text:
            return "serialization"
        if "memoryerror" in text or "cannot allocate memory" in text or "out of memory" in text:
            return "memory"
        return "application"

    async def _notify_owner(self, text: str) -> bool:
        if not self._bot or not settings.owner_id:
            return False
        try:
            await self._bot.send_message(settings.owner_id, text, disable_web_page_preview=True)
            return True
        except Exception as exc:
            log.warning("recovery owner notification failed: %s", exc)
            return False

    async def _journal(
        self,
        *,
        fingerprint: str,
        category: str,
        details: str,
        action: str,
        recovered: bool,
    ) -> None:
        try:
            async with session_factory() as session:
                session.add(
                    RecoveryIncident(
                        fingerprint=fingerprint[:255],
                        category=category[:64],
                        details=details[:4000],
                        action=action[:4000],
                        recovered=bool(recovered),
                        created_at=self._now(),
                    )
                )
                await session.commit()
        except Exception:
            log.exception("failed to persist recovery incident")

    async def start(self, bot: Bot) -> None:
        if self._started:
            return
        self._started = True
        self._bot = bot
        now = self._now()
        previous = self._load_state()
        previous_status = str(previous.get("status") or "")
        previous_unclean = previous_status in {"running", "restarting"}
        restart_attempts = [
            int(x) for x in previous.get("restart_attempts", [])
            if str(x).isdigit() and now - int(x) <= self.RESTART_WINDOW
        ]
        state = {
            "status": "running",
            "session_id": self._session_id,
            "started_at": now,
            "restart_attempts": restart_attempts,
            "last_error": previous.get("last_error", ""),
        }
        self._save_state(state)

        if not previous_unclean:
            return

        recovered = False
        actions: list[str] = []
        try:
            await database_maintenance()
            actions.append("проверила SQLite/WAL и выполнила безопасное обслуживание БД")
            recovered = True
        except Exception as exc:
            actions.append(f"обслуживание БД не удалось: {type(exc).__name__}")
            log.exception("boot recovery database maintenance failed")

        last_error = str(previous.get("last_error") or "неизвестная причина")[:900]
        if recovered:
            await self._notify_owner(
                "✅ <b>Хозяин, я восстановилась после аварийного перезапуска.</b>\n"
                f"Причина прошлого сбоя: <code>{html.escape(last_error)}</code>\n"
                "Что сделала сама:\n• " + "\n• ".join(html.escape(x) for x in actions) +
                "\n• Docker автоматически поднял процесс снова.\n"
                "Сейчас продолжаю работу. Если ошибка повторится несколько раз, я ограничу автоперезапуски и сообщу тебе."
            )
        else:
            await self._notify_owner(
                "⚠️ <b>Хозяин, я перезапустилась после сбоя, но автоматическая проверка не смогла подтвердить полное восстановление.</b>\n"
                f"Последняя ошибка: <code>{html.escape(last_error)}</code>\n"
                "Проверь <code>/recovery</code> и <code>/doctor full</code>."
            )

    async def stop(self) -> None:
        if not self._started:
            return
        state = self._load_state()
        state.update({"status": "clean", "stopped_at": self._now(), "session_id": self._session_id})
        self._save_state(state)
        self._started = False

    def _register_repeat(self, fingerprint: str) -> int:
        now = time.monotonic()
        q = self._errors[fingerprint]
        while q and now - q[0] > self.REPEAT_WINDOW:
            q.popleft()
        q.append(now)
        return len(q)

    async def handle_update_error(self, exc: BaseException, *, context: str = "update") -> bool:
        """Try safe remediation. Return True when an owner-facing report was sent."""
        fp = self.fingerprint(exc)
        category = self.classify(exc)
        repeat_count = self._register_repeat(fp)
        details = redact(f"{type(exc).__name__}: {exc}")[:3500]

        state = self._load_state()
        state["last_error"] = details[:1200]
        state["last_error_fingerprint"] = fp
        state["last_error_at"] = self._now()
        self._save_state(state)

        if category == "database":
            try:
                await database_maintenance()
            except Exception as repair_exc:
                action = f"SQLite maintenance failed: {type(repair_exc).__name__}: {repair_exc}"
                await self._journal(
                    fingerprint=fp, category=category, details=details, action=action, recovered=False
                )
            else:
                action = "PRAGMA optimize + passive WAL checkpoint"
                await self._journal(
                    fingerprint=fp, category=category, details=details, action=action, recovered=True
                )
                return await self._notify_owner(
                    "✅ <b>Хозяин, я поймала сбой SQLite и выполнила безопасное восстановление.</b>\n"
                    f"Ошибка: <code>{html.escape(details[:900])}</code>\n"
                    "Исправлено: проверила соединение с БД, WAL и выполнила обслуживание. Продолжаю работу."
                )

        await self._journal(
            fingerprint=fp,
            category=category,
            details=details,
            action="наблюдение; безопасный restart при повторении" if repeat_count >= 2 else "наблюдение",
            recovered=False,
        )

        if repeat_count >= self.REPEAT_THRESHOLD:
            return await self._schedule_restart(fp, category, details, repeat_count)
        return False

    async def _schedule_restart(self, fp: str, category: str, details: str, repeat_count: int) -> bool:
        if self._restart_task and not self._restart_task.done():
            return True

        state = self._load_state()
        now = self._now()
        attempts = [
            int(x) for x in state.get("restart_attempts", [])
            if str(x).isdigit() and now - int(x) <= self.RESTART_WINDOW
        ]
        if len(attempts) >= self.MAX_RESTARTS_PER_WINDOW:
            state["restart_attempts"] = attempts
            self._save_state(state)
            await self._notify_owner(
                "🛑 <b>Хозяин, автоматические перезапуски временно остановлены.</b>\n"
                f"Одна ошибка повторилась {repeat_count} раз: <code>{html.escape(details[:900])}</code>\n"
                "Я не буду уходить в бесконечный crash-loop. Нужна ручная проверка <code>/recovery</code> и логов."
            )
            return True

        if os.getenv("AUTO_RECOVERY_RESTART", "1").strip().casefold() not in {"1", "true", "yes", "on", "да"}:
            await self._notify_owner(
                "⚠️ Повторный сбой обнаружен, но AUTO_RECOVERY_RESTART отключён.\n"
                f"<code>{html.escape(details[:900])}</code>"
            )
            return True

        attempts.append(now)
        state.update(
            {
                "status": "restarting",
                "restart_attempts": attempts,
                "last_error": details[:1200],
                "last_error_fingerprint": fp,
            }
        )
        self._save_state(state)
        await self._notify_owner(
            "🧰 <b>Хозяин, один и тот же сбой повторяется.</b>\n"
            f"Категория: <code>{html.escape(category)}</code> · повторов: <b>{repeat_count}</b>\n"
            f"Ошибка: <code>{html.escape(details[:800])}</code>\n"
            "Я выполняю безопасный перезапуск процесса. Docker поднимет меня снова, после запуска я проверю БД и напишу результат."
        )
        self._restart_task = asyncio.create_task(self._exit_after_delay(), name="kira-self-restart")
        return True

    async def _exit_after_delay(self) -> None:
        await asyncio.sleep(2.0)
        # Docker compose has restart: unless-stopped. os._exit is intentional here:
        # it turns repeated transient corruption into a clean process restart.
        os._exit(75)

    async def recent(self, limit: int = 10) -> list[RecoveryIncident]:
        try:
            async with session_factory() as session:
                rows = await session.scalars(
                    select(RecoveryIncident).order_by(RecoveryIncident.id.desc()).limit(max(1, min(limit, 30)))
                )
                return list(rows.all())
        except Exception:
            return []

    @staticmethod
    def compact_trace(exc: BaseException, limit: int = 2600) -> str:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return redact(trace)[-limit:]


recovery_runtime = RecoveryRuntime()
