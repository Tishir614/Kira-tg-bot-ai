from __future__ import annotations

from typing import Optional

from pyrogram import Client

from bot import log
from bot.config import settings
from bot.errors import ErrorGetUser


class PyroAPI:
    """Optional MTProto helper.

    The main bot remains fully operational without API_ID/API_HASH. Features that
    need username resolution via MTProto fail locally instead of killing startup.
    """

    _client: Client | None = None
    _started = False

    @classmethod
    def enabled(cls) -> bool:
        return bool(settings.api_id and settings.api_hash and settings.token)

    @classmethod
    def status(cls) -> str:
        if not cls.enabled():
            return "disabled"
        return "started" if cls._started else "configured/not-started"

    @classmethod
    def _get_client(cls) -> Client:
        if not cls.enabled():
            raise ErrorGetUser("Pyrogram is not configured")
        if cls._client is None:
            cls._client = Client(
                name="KiraBot",
                api_id=int(settings.api_id),
                api_hash=settings.api_hash,
                bot_token=settings.token,
                workdir=str(settings.data_dir),
            )
        return cls._client

    @classmethod
    async def start(cls) -> None:
        if not cls.enabled():
            log.warning("Pyrogram disabled: API_ID/API_HASH are not configured")
            return
        if cls._started:
            return
        try:
            await cls._get_client().start()
        except Exception as exc:
            log.warning("Pyrogram helper could not start; username-resolution features will be limited: %s", exc)
            cls._started = False
            return
        cls._started = True
        log.info("Pyrogram helper started")

    @classmethod
    async def stop(cls) -> None:
        if not cls._started or cls._client is None:
            return
        try:
            await cls._client.stop()
        finally:
            cls._started = False

    @classmethod
    async def get_message_text(cls, message_id: int, chat_id: int) -> str | None:
        if not cls._started:
            return None
        try:
            message = await cls._get_client().get_messages(chat_id, message_id)
            return (message.text or message.caption) if message else None
        except Exception as exc:
            log.debug("Pyrogram get_messages failed for %s/%s: %s", chat_id, message_id, exc)
            return None

    @classmethod
    async def get_entity_id(cls, username: str) -> Optional[int]:
        if not cls._started:
            raise ErrorGetUser("Pyrogram helper is unavailable")
        try:
            user = await cls._get_client().get_users(username)
            return user.id
        except Exception as exc:
            log.debug("Pyrogram get_user failed for %s: %s", username, exc)
            raise ErrorGetUser from exc
