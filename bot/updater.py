import html
import json
import logging
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from git import Repo

from bot.bot import bot
from bot.config import settings
from bot.locale import _
from bot.sql import ChatManager
from bot.update_notifier import OwnerUpdateNotifier

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = settings.data_dir


class Updater:
    STATE_FILE = STATIC_DIR / ".updater.json"
    REPO_PATH = BASE_DIR
    PYPROJECT_FILE = BASE_DIR / "pyproject.toml"
    BANNER_FILE = BASE_DIR / "bot" / "media" / "banner.jpg"

    @staticmethod
    async def check():
        try:
            version = Updater._load_version()
            git_hash = "archive"
            git_message = "Обновление установлено. Если что-то сломалось — перезапусти /doctor full."
            if (Updater.REPO_PATH / ".git").exists():
                try:
                    repo = Repo(str(Updater.REPO_PATH))
                    current_commit = repo.head.commit
                    git_hash = current_commit.hexsha[:7]
                    git_message = current_commit.message.strip() or git_message
                except Exception as exc:
                    logger.warning("git metadata unavailable: %s", exc)

            state = Updater._get_state()
            last_version = state.get("version")
            last_hash = state.get("hash")
            if last_version is None:
                Updater._save_state(version, git_hash)
                OwnerUpdateNotifier.mark_initial_install(version, git_hash)
                logger.info("First run. updater state created")
                return

            update_detected = version != last_version or git_hash != last_hash
            # Owner notifier has its own pending state. It is checked on every startup,
            # so a temporary Telegram/network failure is retried after restart.
            await OwnerUpdateNotifier.check(
                current_version=version,
                previous_version=last_version,
                commit_hash=git_hash,
                update_detected=update_detected,
            )

            if update_detected:
                logger.info("Update detected: %s %s", version, git_hash)
                change_log = _(
                    "update_message",
                    version=version,
                    hash=git_hash,
                    message=html.escape(git_message),
                )
                Updater._save_state(version, git_hash)
                await Updater._broadcast(change_log)
        except Exception as e:
            logger.error("updater: %s", e)

    @staticmethod
    def _load_version() -> str:
        import tomllib
        with Updater.PYPROJECT_FILE.open("rb") as f:
            info = tomllib.load(f)
            return str(info.get("project", {}).get("version", "unknown"))

    @staticmethod
    def _get_state() -> dict:
        if Updater.STATE_FILE.exists():
            try:
                return json.loads(Updater.STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _save_state(version: str, commit_hash: str):
        Updater.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        Updater.STATE_FILE.write_text(json.dumps({"version": version, "hash": commit_hash}, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    async def _broadcast(text):
        chats = await ChatManager.get_all()
        me = await bot.get_me()
        support_url = f"https://t.me/{me.username}?start=support"
        if chats:
            for chat in chats:
                # OWNER_ID receives the richer private report from OwnerUpdateNotifier.
                if settings.owner_id is not None and chat.chat_id == settings.owner_id:
                    continue
                try:
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(text="🛟 Поддержка", url=support_url)
                        ]]
                    )
                    await bot.send_photo(
                        chat_id=chat.chat_id,
                        caption=text,
                        photo=FSInputFile(str(Updater.BANNER_FILE)),
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    logger.warning("Notify failed for chat %s: %s", chat.chat_id, e)
