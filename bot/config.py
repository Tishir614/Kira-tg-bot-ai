from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on", "да", "вкл"}


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _env(name)
    try:
        value = int(raw) if raw else int(default)
    except ValueError:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    api_id: str
    api_hash: str
    owner_id: int | None
    timezone: str
    data_dir: Path
    log_level: str
    log_to_file: bool
    log_retention_days: int
    bot_api_base_url: str
    fsm_redis_url: str
    request_limit: int
    request_window_seconds: int
    max_concurrent_ai: int
    max_concurrent_downloads: int
    file_analysis_max_mb: int
    backup_interval_hours: int
    backup_keep: int
    web_panel_enabled: bool
    web_panel_host: str
    web_panel_port: int
    panel_token: str
    support_chat_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        owner_raw = _env("OWNER_ID")
        owner_id = int(owner_raw) if owner_raw.isdigit() and int(owner_raw) > 0 else None
        data_raw = _env("DATA_DIR", "static") or "static"
        data_dir = Path(data_raw)
        if not data_dir.is_absolute():
            data_dir = BASE_DIR / data_dir
        return cls(
            token=_env("TOKEN"),
            api_id=_env("API_ID"),
            api_hash=_env("API_HASH"),
            owner_id=owner_id,
            timezone=_env("BOT_TIMEZONE", "Europe/Vilnius") or "Europe/Vilnius",
            data_dir=data_dir,
            log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
            log_to_file=_env_bool("LOG_TO_FILE", True),
            log_retention_days=_env_int("LOG_RETENTION_DAYS", 14, minimum=1, maximum=365),
            bot_api_base_url=_env("BOT_API_BASE_URL"),
            fsm_redis_url=_env("FSM_REDIS_URL"),
            request_limit=_env_int("REQUEST_LIMIT", 30, minimum=5, maximum=300),
            request_window_seconds=_env_int("REQUEST_WINDOW_SECONDS", 10, minimum=2, maximum=300),
            max_concurrent_ai=_env_int("MAX_CONCURRENT_AI", 4, minimum=1, maximum=64),
            max_concurrent_downloads=_env_int("MAX_CONCURRENT_DOWNLOADS", 3, minimum=1, maximum=32),
            file_analysis_max_mb=_env_int("FILE_ANALYSIS_MAX_MB", 20, minimum=1, maximum=100),
            backup_interval_hours=_env_int("BACKUP_INTERVAL_HOURS", 24, minimum=0, maximum=720),
            backup_keep=_env_int("BACKUP_KEEP", 7, minimum=1, maximum=100),
            web_panel_enabled=_env_bool("WEB_PANEL_ENABLED", False),
            web_panel_host=_env("WEB_PANEL_HOST", "127.0.0.1") or "127.0.0.1",
            web_panel_port=_env_int("WEB_PANEL_PORT", 8080, minimum=1, maximum=65535),
            panel_token=_env("PANEL_TOKEN"),
            support_chat_id=_env("SUPPORT_CHAT_ID", "@kira26481") or "@kira26481",
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.token or ":" not in self.token:
            errors.append("TOKEN не задан или не похож на Telegram bot token")
        if bool(self.api_id) != bool(self.api_hash):
            errors.append("API_ID и API_HASH должны быть заданы вместе")
        elif self.api_id and not self.api_id.isdigit():
            errors.append("API_ID должен быть целым числом")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"Неизвестный BOT_TIMEZONE: {self.timezone}")
        if self.web_panel_enabled:
            weak_panel_token = (
                len(self.panel_token) < 24
                or self.panel_token.lower().startswith(("change_me", "changeme", "replace_me"))
            )
            if weak_panel_token:
                errors.append(
                    "При WEB_PANEL_ENABLED=1 PANEL_TOKEN должен быть случайным секретом "
                    "не короче 24 символов, а не значением из example.env"
                )
        return errors

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "backups").mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
