import logging
import os
import sys
from pathlib import Path  # Для надежного доступа к файлам
from loguru import logger
import tomllib


def load_env_file() -> None:
    """
    Загружает переменные окружения из .env в корне проекта.
    Отсутствие файла не считается ошибкой.
    """
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if not env_path.is_file():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as e:
        logger.warning(f"Не удалось загрузить {env_path.name}: {e}")


load_env_file()

from bot.config import settings
settings.ensure_directories()

# Загрузка конфигурации проекта из pyproject.toml
try:
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    project_info = data["project"]
    version = project_info["version"]
    authors = project_info.get("authors") or []
    developer = (authors[0].get("name") if authors and isinstance(authors[0], dict) else None) \
        or project_info.get("developer", "unknown")
except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError) as e:
    logger.error(f"Ошибка загрузки pyproject.toml: {e}")
    version = "unknown"
    developer = "unknown"

# Формат вывода логов loguru
LOGGER_FORMAT = (
    "<level>{level: <3} | "
    "{message}</level>"
    "<white> - {name}:{function}:{line}</white>"
)

# Настройка loguru: удаляем стандартный handler и добавляем свой
logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format=LOGGER_FORMAT,
    level=settings.log_level,
    backtrace=settings.log_level == "DEBUG",
    diagnose=False,  # Не печатаем значения локальных переменных с потенциальными секретами.
)
if settings.log_to_file:
    logger.add(
        settings.data_dir / "logs" / "kira.log",
        level=settings.log_level,
        rotation="10 MB",
        retention=f"{settings.log_retention_days} days",
        compression="gz",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
    )
logging.getLogger("pyrogram").setLevel(logging.WARNING)


class InterceptHandler(logging.Handler):
    """
    Перехватчик стандартных logging записей для перенаправления в loguru.

    Фильтрует шумные сообщения aiogram и заменяет их на информативные.
    """
    IGNORE = (
        "Start polling", "Run polling for bot",  # Шумные сообщения aiogram
        "Update id=",  # Обновления сообщений
    )

    def emit(self, record):
        from bot.redaction import redact
        message = redact(record.getMessage())
        # Экранирование HTML-тегов для корректного вывода
        message = message.replace('<', '[').replace('>', ']')

        # Фильтрация и замена шумных сообщений
        if any(ig in message for ig in self.IGNORE):
            if "Run polling for bot" in message:
                logger.info("BOT IS STARTED!")  # Информативное сообщение о запуске
            return

        # Определение уровня логирования
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Логирование с контекстом
        logger.opt(
            depth=6,  # Уровень вложенности стека вызовов
            exception=record.exc_info,  # Информация об исключении
            lazy=True  # Отложенная обработка аргументов
        ).log(level, message)


# Настройка стандартного logging для перенаправления через InterceptHandler
logging.basicConfig(
    handlers=[InterceptHandler()],
    level=logging.INFO,
    force=True  # Принудительная переконфигурация всех логгеров
)

# Логгер текущего модуля
log = logging.getLogger(__name__)

# ASCII-баннер бота
banner = """ ____  __.__               
|    |/ _|__|___________   
|      < |  \\_  __ \\__  \\  
|    |  \\|  ||  | \\// __ \\_
|____|__ \\__||__|  (____  /
        \\/              \\/   """

# Информационный блок о запуске
start_info = f'''{'-' * 50}
• Версия:     {version}
• Разработчик: {developer}
{'-' * 50}
'''

def print_start_banner() -> None:
    """Print startup information only when the application is actually launched."""
    print(banner + "\n" + start_info, sep="\n", end="")
