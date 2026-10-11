from __future__ import annotations

import json
import logging
import re
import tomllib
from pathlib import Path
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_FILE = BASE_DIR / "pyproject.toml"
CHANGELOG_FILE = BASE_DIR / "CHANGELOG.md"
TELEGRAM_TEXT_LIMIT = 3900


def _get_bot():
    # Lazy import keeps the formatting helpers testable without creating Bot eagerly.
    from bot.bot import bot

    return bot


def _load_project_metadata() -> tuple[str, str]:
    """Return (version, creator) from pyproject.toml with safe fallbacks."""
    try:
        with PYPROJECT_FILE.open("rb") as handle:
            project = tomllib.load(handle).get("project", {})
        version = str(project.get("version") or "unknown")
        authors = project.get("authors") or []
        creator = "unknown"
        if authors and isinstance(authors[0], dict):
            creator = str(authors[0].get("name") or "unknown")
        return version, creator
    except Exception as exc:
        logger.warning("update notifier metadata unavailable: %s", exc)
        return "unknown", "unknown"


def _strip_markdown(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[-*+]\s+", "• ", line)
    line = re.sub(r"^\d+[.)]\s+", lambda m: m.group(0), line)
    line = line.replace("**", "").replace("__", "").replace("`", "")
    return line.strip()


def _release_notes_from_file(version: str) -> str:
    """Read detailed notes for a release; fall back to CHANGELOG section."""
    release = BASE_DIR / f"RELEASE_{version}.md"
    if release.is_file():
        try:
            lines = release.read_text(encoding="utf-8").splitlines()
            cleaned: list[str] = []
            for index, raw in enumerate(lines):
                text = _strip_markdown(raw)
                if not text:
                    if cleaned and cleaned[-1] != "":
                        cleaned.append("")
                    continue
                # The first H1 only repeats the release title/version.
                if index == 0 and raw.lstrip().startswith("# "):
                    continue
                cleaned.append(text)
            return "\n".join(cleaned).strip()
        except OSError as exc:
            logger.warning("unable to read release notes %s: %s", release, exc)

    if CHANGELOG_FILE.is_file():
        try:
            text = CHANGELOG_FILE.read_text(encoding="utf-8")
            pattern = re.compile(
                rf"(?ms)^##\s+{re.escape(version)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
            )
            match = pattern.search(text)
            if match:
                lines = [_strip_markdown(line) for line in match.group("body").splitlines()]
                return "\n".join(line for line in lines if line).strip()
        except OSError as exc:
            logger.warning("unable to read changelog: %s", exc)

    return "Подробный список изменений для этой сборки не найден."


def _split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split without breaking Telegram message limits, preferring line boundaries."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            start = 0
            while start < len(line):
                chunks.append(line[start : start + limit].rstrip())
                start += limit
            continue
        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return [chunk for chunk in chunks if chunk]


def build_owner_update_messages(
    *,
    previous_version: str | None,
    current_version: str,
    commit_hash: str,
) -> list[str]:
    """Build a detailed, owner-friendly update report in plain text."""
    _metadata_version, creator = _load_project_metadata()
    notes = _release_notes_from_file(current_version)
    previous = previous_version or "неизвестно"
    build = commit_hash or "archive"

    text = (
        "🦊✨ KIRA ОБНОВЛЕНА\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📦 {previous}  ➜  {current_version}\n"
        f"👤 Создатель: {creator}\n"
        f"🔖 Сборка: {build}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🌟 ЧТО НОВОГО\n"
        f"{notes}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Новая версия загружена. Kira запущена и готова к работе.\n"
        "🛟 Если что-то ведёт себя странно, напиши в поддержку кнопкой ниже."
    )
    chunks = _split_message(text)
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    total = len(chunks)
    for index, chunk in enumerate(chunks[1:], start=2):
        prefix = f"🧾 Продолжение обновления {current_version} ({index}/{total})\n\n"
        # Re-split in the unlikely event the prefix pushes a chunk over the limit.
        result.extend(_split_message(prefix + chunk))
    return result


def _admin_chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛟 Поддержка", callback_data="support:start")]]
    )


class OwnerUpdateNotifier:
    """Reliable owner-only update notices with retry-after-restart semantics."""

    STATE_FILE = settings.data_dir / ".owner_update.json"

    @classmethod
    def _load_state(cls) -> dict[str, Any]:
        if not cls.STATE_FILE.exists():
            return {}
        try:
            data = json.loads(cls.STATE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _save_state(cls, state: dict[str, Any]) -> None:
        cls.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = cls.STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(cls.STATE_FILE)

    @classmethod
    def mark_initial_install(cls, current_version: str, commit_hash: str) -> None:
        """Baseline a clean install so it is not mistaken for an update."""
        if cls._load_state():
            return
        cls._save_state(
            {
                "last_notified_version": current_version,
                "last_notified_hash": commit_hash,
                "pending": None,
            }
        )

    @classmethod
    async def check(
        cls,
        *,
        current_version: str,
        previous_version: str | None,
        commit_hash: str,
        update_detected: bool,
    ) -> bool:
        state = cls._load_state()
        pending = state.get("pending") if isinstance(state.get("pending"), dict) else None

        if pending and pending.get("to") == current_version and pending.get("hash") == commit_hash:
            payload = pending
        elif update_detected:
            if (
                state.get("last_notified_version") == current_version
                and state.get("last_notified_hash") == commit_hash
            ):
                return False
            payload = {
                "from": previous_version,
                "to": current_version,
                "hash": commit_hash,
            }
            state["pending"] = payload
            cls._save_state(state)
        else:
            return False

        if not settings.owner_id:
            logger.warning("OWNER_ID is not configured; detailed update notice remains pending")
            return False

        messages = build_owner_update_messages(
            previous_version=str(payload.get("from") or "неизвестно"),
            current_version=current_version,
            commit_hash=commit_hash,
        )
        try:
            telegram_bot = _get_bot()
            for message in messages:
                await telegram_bot.send_message(
                    chat_id=settings.owner_id,
                    text=message,
                    parse_mode=None,
                    disable_web_page_preview=True,
                    reply_markup=_admin_chat_keyboard(),
                )
        except Exception as exc:
            logger.warning("owner update notification failed, will retry after restart: %s", exc)
            return False

        cls._save_state(
            {
                "last_notified_version": current_version,
                "last_notified_hash": commit_hash,
                "pending": None,
            }
        )
        logger.info("Detailed update notice sent to owner for %s (%s)", current_version, commit_hash)
        return True
