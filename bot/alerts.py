"""Owner alerts: notify when AI requests start failing en masse, and when they recover."""
from __future__ import annotations

import asyncio
import html
import time
from collections import deque

from bot import log

WINDOW = 10
FAIL_THRESHOLD = 8      # failures among the last WINDOW outcomes
RECOVER_STREAK = 5      # consecutive successes that count as recovered
COOLDOWN = 1800         # seconds between repeated alerts
CHECK_EVERY = 30


class AIHealthMonitor:
    def __init__(self) -> None:
        self.outcomes: deque[bool] = deque(maxlen=WINDOW)
        self.alerted_at = 0.0
        self.in_alert = False

    def record(self, ok: bool) -> None:
        self.outcomes.append(bool(ok))

    def evaluate(self, now: float | None = None) -> str | None:
        """Return 'alert', 'recovered' or None; mutates alert state."""
        now = time.monotonic() if now is None else now
        results = list(self.outcomes)
        fails = results.count(False)
        if not self.in_alert:
            if len(results) >= WINDOW and fails >= FAIL_THRESHOLD and (
                not self.alerted_at or now - self.alerted_at >= COOLDOWN
            ):
                self.in_alert, self.alerted_at = True, now
                return "alert"
            return None
        if len(results) >= RECOVER_STREAK and all(results[-RECOVER_STREAK:]):
            self.in_alert = False
            return "recovered"
        return None


monitor = AIHealthMonitor()


class AlertRuntime:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self, bot) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(bot), name="kira-alerts")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _notify(self, bot, text: str) -> None:
        from bot.owners import owner_ids

        for owner in owner_ids():
            try:
                await bot.send_message(owner, text)
            except Exception:
                log.debug("alert delivery failed", exc_info=True)

    async def _loop(self, bot) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=CHECK_EVERY)
                return
            except asyncio.TimeoutError:
                pass
            try:
                state = monitor.evaluate()
                if state == "alert":
                    from bot.ai_client import ai

                    await self._notify(
                        bot,
                        "🚨 <b>AI Киры почти не отвечает:</b> "
                        f"{FAIL_THRESHOLD} из последних {WINDOW} запросов завершились ошибкой.\n"
                        f"Провайдер: <code>{html.escape(ai.provider_name)}</code>. Проверь <code>/ai_health</code> и Ollama.",
                    )
                elif state == "recovered":
                    await self._notify(bot, "✅ AI Киры снова отвечает нормально.")
            except Exception:
                log.exception("alert loop failed")


alert_runtime = AlertRuntime()
