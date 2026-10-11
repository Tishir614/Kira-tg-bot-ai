import asyncio

from bot import print_start_banner
from bot.bot import bot, init_bot
from bot.pyrogram_core import PyroAPI
from bot.updater import Updater


async def on_startup() -> None:
    """Подготовка сервисов перед запуском polling."""
    print_start_banner()
    await Updater.check()
    await PyroAPI.start()


async def main() -> None:
    """Запускает бота и гарантированно закрывает внешние клиенты."""
    await on_startup()
    try:
        # init_bot() живёт до остановки polling, дополнительный бесконечный Event
        # после него не нужен и мешал нормальному завершению процесса.
        await init_bot()
    finally:
        try:
            await PyroAPI.stop()
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
