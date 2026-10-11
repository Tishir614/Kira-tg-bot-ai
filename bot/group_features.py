from __future__ import annotations

import html
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bot import log
from bot.sql import session_factory
from bot.sql.orm_tables import AuditLog, GroupActivity, GroupConversationSettings, GroupReport, GroupRulesSettings, Warn


ACTIVITY_XP_PER_MESSAGE = 3


def activity_level_for_xp(total_xp: int) -> int:
    """Cumulative progression: 100 XP for L2, then +200, +300, ..."""
    xp = max(0, int(total_xp))
    level = 1
    remaining = xp
    while level < 100 and remaining >= 100 * level:
        remaining -= 100 * level
        level += 1
    return level


def activity_progress(total_xp: int) -> tuple[int, int, int]:
    """Return (level, xp_inside_level, xp_needed_for_next_level)."""
    xp = max(0, int(total_xp))
    level = 1
    remaining = xp
    while level < 100 and remaining >= 100 * level:
        remaining -= 100 * level
        level += 1
    return level, remaining, 100 * level


class GroupActivityManager:
    @staticmethod
    async def record(message: Message) -> GroupActivity | None:
        user = message.from_user
        if not user or user.is_bot or message.chat.type == "private":
            return None

        text_inc = 1 if (message.text or message.caption) else 0
        voice_inc = 1 if (message.voice or message.video_note) else 0
        media_inc = 1 if any(
            (
                message.photo,
                message.video,
                message.animation,
                message.document,
                message.audio,
                message.sticker,
                message.voice,
                message.video_note,
            )
        ) else 0
        now = int(time.time())
        display_name = (user.full_name or user.username or str(user.id))[:180]
        username = (user.username or "")[:64] or None

        async with session_factory() as session:
            stmt = sqlite_insert(GroupActivity).values(
                chat_id=message.chat.id,
                user_id=user.id,
                display_name=display_name,
                username=username,
                message_count=1,
                text_messages=text_inc,
                media_messages=media_inc,
                voice_messages=voice_inc,
                activity_xp=ACTIVITY_XP_PER_MESSAGE,
                activity_level=1,
                last_message_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[GroupActivity.chat_id, GroupActivity.user_id],
                set_={
                    "display_name": display_name,
                    "username": username,
                    "message_count": GroupActivity.message_count + 1,
                    "text_messages": GroupActivity.text_messages + text_inc,
                    "media_messages": GroupActivity.media_messages + media_inc,
                    "voice_messages": GroupActivity.voice_messages + voice_inc,
                    "activity_xp": GroupActivity.activity_xp + ACTIVITY_XP_PER_MESSAGE,
                    "last_message_at": now,
                },
            )
            await session.execute(stmt)
            row = await session.scalar(
                select(GroupActivity).where(
                    GroupActivity.chat_id == message.chat.id,
                    GroupActivity.user_id == user.id,
                )
            )
            if row is not None:
                row.activity_level = activity_level_for_xp(int(row.activity_xp or 0))
            await session.commit()
            if row is not None:
                await session.refresh(row)
            return row

    @staticmethod
    async def get(chat_id: int, user_id: int) -> GroupActivity | None:
        async with session_factory() as session:
            return await session.scalar(
                select(GroupActivity).where(
                    GroupActivity.chat_id == chat_id,
                    GroupActivity.user_id == user_id,
                )
            )

    @staticmethod
    async def top(chat_id: int, limit: int = 15) -> list[GroupActivity]:
        limit = max(1, min(int(limit), 50))
        async with session_factory() as session:
            rows = await session.scalars(
                select(GroupActivity)
                .where(GroupActivity.chat_id == chat_id)
                .order_by(
                    GroupActivity.activity_level.desc(),
                    GroupActivity.activity_xp.desc(),
                    GroupActivity.message_count.desc(),
                    GroupActivity.user_id.asc(),
                )
                .limit(limit)
            )
            return list(rows.all())

    @staticmethod
    async def totals(chat_id: int) -> dict[str, int]:
        async with session_factory() as session:
            messages = await session.scalar(
                select(func.coalesce(func.sum(GroupActivity.message_count), 0)).where(
                    GroupActivity.chat_id == chat_id
                )
            )
            users = await session.scalar(
                select(func.count()).select_from(GroupActivity).where(GroupActivity.chat_id == chat_id)
            )
            return {"messages": int(messages or 0), "users": int(users or 0)}


class GroupConversationSettingsManager:
    @staticmethod
    async def get(chat_id: int) -> GroupConversationSettings:
        async with session_factory() as session:
            row = await session.get(GroupConversationSettings, chat_id)
            if row is None:
                row = GroupConversationSettings(chat_id=chat_id)
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def update(chat_id: int, **values: Any) -> GroupConversationSettings:
        allowed = {"enabled", "spontaneous_chance", "cooldown_seconds", "last_spoke_at"}
        async with session_factory() as session:
            row = await session.get(GroupConversationSettings, chat_id)
            if row is None:
                row = GroupConversationSettings(chat_id=chat_id)
                session.add(row)
            for key, value in values.items():
                if key not in allowed:
                    continue
                if key == "spontaneous_chance":
                    value = max(0, min(25, int(value)))
                elif key == "cooldown_seconds":
                    value = max(120, min(7200, int(value)))
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row


class GroupRulesSettingsManager:
    @staticmethod
    async def get(chat_id: int) -> GroupRulesSettings:
        async with session_factory() as session:
            row = await session.get(GroupRulesSettings, chat_id)
            if row is None:
                row = GroupRulesSettings(chat_id=chat_id, enabled=True, updated_at=int(time.time()))
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def set_enabled(chat_id: int, enabled: bool) -> GroupRulesSettings:
        async with session_factory() as session:
            row = await session.get(GroupRulesSettings, chat_id)
            if row is None:
                row = GroupRulesSettings(chat_id=chat_id)
                session.add(row)
            row.enabled = bool(enabled)
            row.updated_at = int(time.time())
            await session.commit()
            await session.refresh(row)
            return row


class WarningManager:
    @staticmethod
    async def add(user_id: int, chat_id: int, cause: str, now: int | None = None) -> int:
        now = int(now or time.time())
        async with session_factory() as session:
            session.add(
                Warn(
                    user_id=user_id,
                    chat_id=chat_id,
                    cause=(cause or "Без причины")[:1000],
                    created_at=now,
                    time=0.0,
                )
            )
            await session.commit()
            return int(
                (await session.scalar(
                    select(func.count()).select_from(Warn).where(
                        Warn.chat_id == chat_id, Warn.user_id == user_id
                    )
                ))
                or 0
            )

    @staticmethod
    async def count(user_id: int, chat_id: int) -> int:
        async with session_factory() as session:
            return int(
                (await session.scalar(
                    select(func.count()).select_from(Warn).where(
                        Warn.chat_id == chat_id, Warn.user_id == user_id
                    )
                ))
                or 0
            )

    @staticmethod
    async def latest(user_id: int, chat_id: int, limit: int = 10) -> list[Warn]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(Warn)
                .where(Warn.chat_id == chat_id, Warn.user_id == user_id)
                .order_by(Warn.id.desc())
                .limit(max(1, min(limit, 25)))
            )
            return list(rows.all())

    @staticmethod
    async def remove_latest(user_id: int, chat_id: int) -> bool:
        async with session_factory() as session:
            row = await session.scalar(
                select(Warn)
                .where(Warn.chat_id == chat_id, Warn.user_id == user_id)
                .order_by(Warn.id.desc())
                .limit(1)
            )
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    @staticmethod
    async def clear(user_id: int, chat_id: int) -> int:
        async with session_factory() as session:
            result = await session.execute(
                delete(Warn).where(Warn.chat_id == chat_id, Warn.user_id == user_id)
            )
            await session.commit()
            return int(result.rowcount or 0)


class GroupAuditManager:
    @staticmethod
    async def recent(chat_id: int, limit: int = 12) -> list[AuditLog]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(AuditLog)
                .where(AuditLog.chat_id == chat_id)
                .order_by(AuditLog.id.desc())
                .limit(max(1, min(int(limit), 50)))
            )
            return list(rows.all())


class GroupReportManager:
    MAX_REPORTS_PER_DAY = 8
    DUPLICATE_WINDOW_SECONDS = 10 * 60

    @staticmethod
    async def create(
        *,
        chat_id: int,
        reporter_id: int,
        target_id: int,
        target_name: str,
        message_id: int,
        message_text: str,
        reason: str,
        now: int | None = None,
    ) -> tuple[GroupReport, bool]:
        now = int(now or time.time())
        async with session_factory() as session:
            duplicate = await session.scalar(
                select(GroupReport)
                .where(
                    GroupReport.chat_id == chat_id,
                    GroupReport.reporter_id == reporter_id,
                    GroupReport.target_id == target_id,
                    GroupReport.message_id == message_id,
                    GroupReport.status == "open",
                    GroupReport.created_at >= now - GroupReportManager.DUPLICATE_WINDOW_SECONDS,
                )
                .order_by(GroupReport.id.desc())
                .limit(1)
            )
            if duplicate is not None:
                return duplicate, False

            recent_count = await session.scalar(
                select(func.count()).select_from(GroupReport).where(
                    GroupReport.chat_id == chat_id,
                    GroupReport.reporter_id == reporter_id,
                    GroupReport.created_at >= now - 86400,
                )
            )
            if int(recent_count or 0) >= GroupReportManager.MAX_REPORTS_PER_DAY:
                raise ValueError("Слишком много жалоб за сутки. Попробуй позже.")

            row = GroupReport(
                chat_id=chat_id,
                reporter_id=reporter_id,
                target_id=target_id,
                target_name=(target_name or f"ID {target_id}")[:180],
                message_id=int(message_id or 0),
                message_text=(message_text or "")[:1800],
                reason=(reason or "Без причины")[:1000],
                status="open",
                created_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row, True

    @staticmethod
    async def get(report_id: int, chat_id: int | None = None) -> GroupReport | None:
        async with session_factory() as session:
            stmt = select(GroupReport).where(GroupReport.id == int(report_id))
            if chat_id is not None:
                stmt = stmt.where(GroupReport.chat_id == int(chat_id))
            return await session.scalar(stmt)

    @staticmethod
    async def recent(chat_id: int, *, status: str | None = "open", limit: int = 15) -> list[GroupReport]:
        async with session_factory() as session:
            stmt = select(GroupReport).where(GroupReport.chat_id == chat_id)
            if status:
                stmt = stmt.where(GroupReport.status == status)
            rows = await session.scalars(
                stmt.order_by(GroupReport.id.desc()).limit(max(1, min(int(limit), 50)))
            )
            return list(rows.all())

    @staticmethod
    async def close(
        report_id: int,
        *,
        chat_id: int,
        handled_by: int,
        status: str,
        resolution: str = "",
        now: int | None = None,
    ) -> GroupReport | None:
        if status not in {"resolved", "rejected"}:
            raise ValueError("invalid report status")
        async with session_factory() as session:
            row = await session.scalar(
                select(GroupReport).where(
                    GroupReport.id == int(report_id),
                    GroupReport.chat_id == int(chat_id),
                )
            )
            if row is None:
                return None
            row.status = status
            row.handled_by = int(handled_by)
            row.handled_at = int(now or time.time())
            row.resolution = (resolution or "")[:1000]
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def stats(chat_id: int) -> dict[str, int]:
        async with session_factory() as session:
            values = {}
            for status in ("open", "resolved", "rejected"):
                values[status] = int(
                    (await session.scalar(
                        select(func.count()).select_from(GroupReport).where(
                            GroupReport.chat_id == chat_id, GroupReport.status == status
                        )
                    ))
                    or 0
                )
            return values


class ActivityTrackingMiddleware(BaseMiddleware):
    """Count every human group message even when another handler consumes it."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type != "private":
            try:
                await GroupActivityManager.record(event)
            except Exception:
                log.exception("group activity tracking failed")
        return await handler(event, data)


activity_tracking_middleware = ActivityTrackingMiddleware()


def format_activity_name(row: GroupActivity) -> str:
    name = html.escape(row.display_name or f"ID {row.user_id}")
    return f"<a href='tg://user?id={row.user_id}'>{name}</a>"
