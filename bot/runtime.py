from __future__ import annotations

import asyncio
import html
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot import log
from bot.backups import create_persistent_database_backup
from bot.config import settings
from bot.middlewares import request_rate_limit
from bot.moderation import moderation_service
from bot.sql import ChatSettingsManager, ReminderManager, cleanup_old_data, database_maintenance


@dataclass(slots=True)
class RuntimeMetrics:
    started_at: float = field(default_factory=time.time)
    errors: int = 0
    ai_requests: int = 0
    downloads: int = 0
    searches: int = 0
    reminders_sent: int = 0
    backups_created: int = 0

    @property
    def uptime(self) -> int:
        return max(0, int(time.time() - self.started_at))


metrics = RuntimeMetrics()


class ReminderRuntime:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self, bot: Bot) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(bot), name="kira-reminders")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, bot: Bot) -> None:
        while not self._stop.is_set():
            now = int(time.time())
            try:
                rows = await ReminderManager.due(now)
                for row in rows:
                    try:
                        await bot.send_message(row.chat_id, f"⏰ <b>Напоминание</b>\n{row.text}")
                    except (TelegramForbiddenError, TelegramBadRequest) as exc:
                        # Permanent-ish delivery failures should not hammer Telegram forever.
                        log.warning("Reminder %s disabled after Telegram rejection: %s", row.id, exc)
                        await ReminderManager.complete(row.id, now)
                    except Exception as exc:
                        # Network/service errors are retried after five minutes instead of being lost.
                        log.warning("Reminder %s delivery deferred: %s", row.id, exc)
                        await ReminderManager.defer(row.id, now + 300)
                    else:
                        await ReminderManager.complete(row.id, now)
                        metrics.reminders_sent += 1
            except Exception:
                metrics.errors += 1
                log.exception("Reminder loop failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass


class MaintenanceRuntime:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="kira-maintenance")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        # Small maintenance cycle hourly; backup cadence is independently configurable.
        last_backup = 0.0
        while not self._stop.is_set():
            now = time.time()
            try:
                request_rate_limit.cleanup()
                moderation_service.cleanup()
                try:
                    from bot.social import kira_social
                    kira_social.cleanup()
                except Exception:
                    log.exception("Kira social cleanup failed")
                await database_maintenance()
                pruned = await cleanup_old_data(int(now))
                if pruned["audit"] or pruned["reminders"]:
                    log.info("Pruned old rows: %s", pruned)
                interval = settings.backup_interval_hours * 3600
                if interval > 0 and (not last_backup or now - last_backup >= interval):
                    path = await create_persistent_database_backup()
                    last_backup = now
                    metrics.backups_created += 1
                    log.info("Database backup created: %s", path)
            except Exception:
                metrics.errors += 1
                log.exception("Maintenance cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                pass


reminder_runtime = ReminderRuntime()
maintenance_runtime = MaintenanceRuntime()


class ProactiveVoiceRuntime:
    """Opt-in spontaneous Kira voice notes.

    The feature is deliberately conservative: disabled by default, respects
    quiet hours and a 3-hour per-chat cooldown, and never sends mature/sexual
    material on its own.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self, bot: Bot) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(bot), name="kira-auto-voice")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _send(self, bot: Bot, chat_id: int) -> None:
        from bot.ai_client import AIUnavailable, ai
        phrases = [
            "Я тут, хвостик на месте. Как вы сегодня?",
            "Лисья проверка связи. Надеюсь, у вас всё хорошо.",
            "Я ненадолго заглянула в чат. Кто чем занят?",
            "Мур, решила просто оставить вам голосовой привет.",
            "Хвостом махнула и пришла пожелать вам хорошего вечера.",
        ]
        text = random.choice(phrases)
        if ai.enabled:
            try:
                text = await ai.respond(
                    "Напиши одну короткую естественную реплику от Киры-лисицы для дружеского чата, 6–16 слов. "
                    "Без сексуального содержания, без рекламы и без вопросов о личных данных.",
                    user_id=0, chat_id=chat_id, remember=False,
                )
            except AIUnavailable:
                pass
            except Exception:
                pass
        audio = await ai.speech(text)
        await bot.send_voice(
            chat_id,
            BufferedInputFile(audio, filename="kira-auto.ogg"),
            caption=f"🦊 {html.escape(text[:800])}",
        )

    async def _loop(self, bot: Bot) -> None:
        while not self._stop.is_set():
            now = int(time.time())
            try:
                hour = datetime.now(ZoneInfo(settings.timezone)).hour
                if 9 <= hour < 23:
                    rows = await ChatSettingsManager.auto_voice_chats()
                    for row in rows:
                        if now - int(row.last_auto_voice_at or 0) < 3 * 3600:
                            continue
                        chance = max(1, min(100, int(row.auto_voice_chance or 20)))
                        if random.randint(1, 100) > chance:
                            continue
                        try:
                            await self._send(bot, row.chat_id)
                            await ChatSettingsManager.update(row.chat_id, last_auto_voice_at=now)
                        except (TelegramForbiddenError, TelegramBadRequest) as exc:
                            log.warning("Auto voice disabled for chat %s: %s", row.chat_id, exc)
                            await ChatSettingsManager.update(row.chat_id, auto_voice=False)
                        except Exception:
                            metrics.errors += 1
                            log.exception("Auto voice failed for chat %s", row.chat_id)
            except Exception:
                metrics.errors += 1
                log.exception("Auto voice loop failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=1800)
            except asyncio.TimeoutError:
                pass


proactive_voice_runtime = ProactiveVoiceRuntime()


class ServiceWatchdogRuntime:
    """Restart background tasks that unexpectedly stop without restarting the whole bot."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self, bot: Bot) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(bot), name="kira-service-watchdog")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _notify_fixed(self, bot: Bot, component: str, details: str) -> None:
        if not settings.owner_id:
            return
        try:
            await bot.send_message(
                settings.owner_id,
                f"✅ <b>Хозяин, я сама восстановила сервис:</b> <code>{html.escape(component)}</code>\n"
                f"{html.escape(details[:1200])}",
            )
        except Exception:
            pass

    async def _loop(self, bot: Bot) -> None:
        # Give services time to finish their initial startup before the first probe.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=45)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                # Uvicorn runs as its own task. If it dies, restart just the web service.
                from bot.web_panel import web_panel_runtime
                web_task = web_panel_runtime.task
                if web_task is not None and web_task.done():
                    try:
                        exc = web_task.exception()
                    except (asyncio.CancelledError, Exception) as err:
                        exc = err
                    log.error("Web service task stopped unexpectedly: %r", exc)
                    web_panel_runtime.task = None
                    web_panel_runtime.server = None
                    await web_panel_runtime.start()
                    if web_panel_runtime.task is not None and not web_panel_runtime.task.done():
                        await self._notify_fixed(
                            bot,
                            "D&D/Web",
                            "Веб-сервис неожиданно остановился. Я перезапустила только его, без перезапуска всего бота.",
                        )

                # Reminder/voice loops are also isolated so one failed task does not take Kira down.
                if reminder_runtime._task is not None and reminder_runtime._task.done():
                    reminder_runtime._task = None
                    await reminder_runtime.start(bot)
                    await self._notify_fixed(bot, "reminders", "Фоновый цикл напоминаний был поднят заново.")

                if proactive_voice_runtime._task is not None and proactive_voice_runtime._task.done():
                    proactive_voice_runtime._task = None
                    await proactive_voice_runtime.start(bot)
                    await self._notify_fixed(bot, "auto-voice", "Фоновый цикл авто-голосовых был поднят заново.")
            except Exception:
                metrics.errors += 1
                log.exception("Service watchdog probe failed")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass


service_watchdog_runtime = ServiceWatchdogRuntime()
