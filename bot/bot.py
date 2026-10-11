from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from bot import log
from bot.config import settings
from bot.handlers import get_include_routers
from bot.http_client import http_client
from bot.middlewares import request_rate_limit, russian_command_alias_middleware, usage_stats_middleware
from bot.group_features import activity_tracking_middleware
from bot.group_rules import group_rules_middleware
from bot.kira_next import kira_next_middleware
from bot.help_ui import telegram_menu_commands
from bot.recovery import recovery_runtime
from bot.runtime import maintenance_runtime, proactive_voice_runtime, reminder_runtime, service_watchdog_runtime
from bot.sql import RPManager, add_default, create_tables, engine
from bot.storage import create_fsm_storage
from bot.web_panel import web_panel_runtime


_errors = settings.validate()
if _errors:
    raise RuntimeError("Ошибка конфигурации KiraBot: " + "; ".join(_errors))

api_session = None
if settings.bot_api_base_url:
    api_session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.bot_api_base_url.rstrip("/"), is_local=True)
    )

bot = Bot(
    token=settings.token,
    session=api_session,
    default=DefaultBotProperties(parse_mode="HTML"),
)

rp_manager = RPManager()


async def _set_command_menu() -> None:
    # Keep Telegram's slash menu tidy. /help contains the complete categorized index.
    try:
        await bot.set_my_commands(telegram_menu_commands())
    except Exception as exc:
        log.warning("Unable to set Telegram command menu: %s", exc)


async def init_bot() -> Bot:
    """Initialize storage/services, run polling and close everything cleanly."""
    await create_tables()
    await rp_manager.load_all_triggers()
    await rp_manager.load_default()
    # Старые сборки содержали два взрослых RP-триггера с слишком графичными
    # формулировками. SQL-файл заморожен ради обратной совместимости модуля
    # статистики, поэтому безопасно переопределяем только runtime-представление.
    safe_legacy_rp = {
        "трахнуть": "{u1} предложил(а) {u2} взрослое RP-действие (нужно взаимное согласие)",
        "отсосать": "{u1} предложил(а) {u2} интимное RP-действие (нужно взаимное согласие)",
    }
    for trigger_name, safe_answer in safe_legacy_rp.items():
        item = rp_manager.objects.get((0, trigger_name))
        if item is not None:
            item.answer = safe_answer
    await add_default()

    storage = create_fsm_storage()
    dp = Dispatcher(storage=storage)
    # Cyrillic command aliases must run before filters and other message middleware.
    dp.message.outer_middleware(russian_command_alias_middleware)
    dp.message.outer_middleware(usage_stats_middleware)
    dp.message.outer_middleware(request_rate_limit)
    dp.message.outer_middleware(activity_tracking_middleware)
    dp.message.outer_middleware(group_rules_middleware)
    dp.message.outer_middleware(kira_next_middleware)
    dp.callback_query.outer_middleware(request_rate_limit)
    dp.include_router(get_include_routers())

    await _set_command_menu()
    await recovery_runtime.start(bot)
    await reminder_runtime.start(bot)
    await proactive_voice_runtime.start(bot)
    await maintenance_runtime.start()
    await web_panel_runtime.start()
    await service_watchdog_runtime.start(bot)
    log.info("KiraBot services initialized")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=False,
        )
    finally:
        await service_watchdog_runtime.stop()
        await reminder_runtime.stop()
        await proactive_voice_runtime.stop()
        await maintenance_runtime.stop()
        await web_panel_runtime.stop()
        await http_client.close()
        try:
            await storage.close()
        finally:
            try:
                await engine.dispose()
            finally:
                await recovery_runtime.stop()
    return bot
