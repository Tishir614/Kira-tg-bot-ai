from __future__ import annotations

import html

from aiogram import Bot, Router
from aiogram.types import ErrorEvent

from bot import log
from bot.config import settings
from bot.recovery import recovery_runtime
from bot.runtime import metrics

router = Router(name="errors")


@router.errors()
async def global_error_handler(event: ErrorEvent, bot: Bot):
    metrics.errors += 1
    log.error("Unhandled update error: %r", event.exception, exc_info=event.exception)

    reported = False
    try:
        reported = await recovery_runtime.handle_update_error(
            event.exception,
            context=type(getattr(event, "update", None)).__name__,
        )
    except Exception:
        log.exception("automatic recovery handler failed")

    if not reported and settings.owner_id:
        trace = recovery_runtime.compact_trace(event.exception, 2600)
        try:
            await bot.send_message(
                settings.owner_id,
                "🚨 <b>KiraBot: необработанная ошибка</b>\n"
                "Я записала её в журнал восстановления и слежу за повторениями. "
                "Если одна и та же ошибка повторится несколько раз, выполню ограниченный безопасный рестарт.\n\n"
                "<pre>" + html.escape(trace) + "</pre>",
            )
        except Exception:
            pass
    return True
