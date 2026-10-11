from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time
from dataclasses import dataclass

from aiogram.types import Message
from sqlalchemy import delete, select

from bot import log
from bot.ai_client import ai
from bot.sql import NicknameManager, session_factory
from bot.sql.orm_tables import (
    AIModerationIncident,
    ChatMemoryMessage,
    ChatMemorySettings,
    LongTermMemory,
    MemoryEvent,
    MemoryPrivacy,
    PendingAdminAction,
    UserNickname,
)

_TOKEN_RE = re.compile(r"[\wа-яё]{2,}", re.I)
_URL_RE = re.compile(r"https?://|t\.me/|telegram\.me/|www\.", re.I)
_SUSPICIOUS_RE = re.compile(
    r"\b(?:скам|scam|airdrop|seed\s*phrase|кошел[её]к|парол|логин|убью|сдохни|тварь|мразь|идиот|дебил|спам|spam|рейд|raid)\w*\b",
    re.I,
)
_DECISION_RE = re.compile(r"\b(?:решили|решение|договорились|итог|утвердили|выбрали)\b", re.I)


def _tokens(text: str) -> list[str]:
    return [x.casefold() for x in _TOKEN_RE.findall(text or "")][:700]


def semantic_signature(text: str, dims: int = 64) -> str:
    vec = [0.0] * dims
    tokens = _tokens(text)
    features = list(tokens)
    joined = " ".join(tokens)
    features.extend(joined[i:i + 3] for i in range(max(0, len(joined) - 2)))
    for feature in features[:1600]:
        h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        vec[h % dims] += -1.0 if ((h >> 8) & 1) else 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return json.dumps([round(x / norm, 5) for x in vec], separators=(",", ":"))


def _similarity(a: str, b: str) -> float:
    try:
        va, vb = json.loads(a), json.loads(b)
        return sum(float(x) * float(y) for x, y in zip(va, vb))
    except Exception:
        return 0.0


class PrivacyManager:
    @staticmethod
    async def get(user_id: int) -> MemoryPrivacy:
        async with session_factory() as session:
            row = await session.get(MemoryPrivacy, user_id)
            if row is None:
                row = MemoryPrivacy(user_id=user_id, updated_at=int(time.time()))
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def update(user_id: int, **values) -> MemoryPrivacy:
        allowed = {"personal_memory", "allow_group_history", "allow_profile_learning"}
        async with session_factory() as session:
            row = await session.get(MemoryPrivacy, user_id)
            if row is None:
                row = MemoryPrivacy(user_id=user_id)
                session.add(row)
            for key, value in values.items():
                if key in allowed:
                    setattr(row, key, bool(value))
            row.updated_at = int(time.time())
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def forget_user(user_id: int) -> dict[str, int]:
        result: dict[str, int] = {}
        async with session_factory() as session:
            for label, model in (("long_term", LongTermMemory), ("history", ChatMemoryMessage), ("nicknames", UserNickname)):
                deleted = await session.execute(delete(model).where(model.user_id == user_id))
                result[label] = int(deleted.rowcount or 0)
            await session.execute(delete(MemoryPrivacy).where(MemoryPrivacy.user_id == user_id))
            await session.commit()
        return result


class ChatMemoryManager:
    @staticmethod
    async def settings(chat_id: int) -> ChatMemorySettings:
        async with session_factory() as session:
            row = await session.get(ChatMemorySettings, chat_id)
            if row is None:
                row = ChatMemorySettings(chat_id=chat_id, updated_at=int(time.time()))
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def update_settings(chat_id: int, **values) -> ChatMemorySettings:
        allowed = {"enabled", "retention_days", "personality", "speech_style", "moderator_mode", "moderator_strictness", "digest_enabled"}
        async with session_factory() as session:
            row = await session.get(ChatMemorySettings, chat_id)
            if row is None:
                row = ChatMemorySettings(chat_id=chat_id)
                session.add(row)
            for key, value in values.items():
                if key in allowed:
                    setattr(row, key, value)
            row.updated_at = int(time.time())
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def ingest(message: Message) -> None:
        if not message.from_user or not message.text or message.chat.type == "private":
            return
        cfg = await ChatMemoryManager.settings(message.chat.id)
        if not cfg.enabled:
            return
        privacy = await PrivacyManager.get(message.from_user.id)
        if not privacy.allow_group_history:
            return
        text = message.text.replace("\x00", " ").strip()[:5000]
        if not text:
            return
        now = int(time.time())
        display_name = (await NicknameManager.get(message.from_user.id, message.chat.id) or message.from_user.full_name)[:180]
        async with session_factory() as session:
            exists = await session.scalar(
                select(ChatMemoryMessage.id).where(
                    ChatMemoryMessage.chat_id == message.chat.id,
                    ChatMemoryMessage.message_id == message.message_id,
                )
            )
            if not exists:
                session.add(
                    ChatMemoryMessage(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        user_id=message.from_user.id,
                        display_name=display_name,
                        text=text,
                        semantic_hash=semantic_signature(text),
                        created_at=now,
                    )
                )
                if _DECISION_RE.search(text):
                    session.add(
                        MemoryEvent(
                            chat_id=message.chat.id,
                            user_id=message.from_user.id,
                            event_type="decision",
                            summary=text[:1200],
                            source_message_id=message.message_id,
                            created_at=now,
                        )
                    )
                await session.commit()
        await ChatMemoryManager.cleanup(message.chat.id, cfg.retention_days)

    @staticmethod
    async def cleanup(chat_id: int, retention_days: int) -> None:
        cutoff = int(time.time()) - max(1, min(365, int(retention_days or 30))) * 86400
        async with session_factory() as session:
            await session.execute(
                delete(ChatMemoryMessage).where(
                    ChatMemoryMessage.chat_id == chat_id,
                    ChatMemoryMessage.created_at < cutoff,
                )
            )
            await session.commit()

    @staticmethod
    async def search(chat_id: int, query: str, limit: int = 8) -> list[ChatMemoryMessage]:
        sig = semantic_signature(query)
        async with session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(ChatMemoryMessage)
                        .where(ChatMemoryMessage.chat_id == chat_id)
                        .order_by(ChatMemoryMessage.id.desc())
                        .limit(800)
                    )
                ).all()
            )
        query_tokens = set(_tokens(query))

        def score(row: ChatMemoryMessage) -> float:
            lexical = len(query_tokens & set(_tokens(row.text))) / (len(query_tokens) or 1)
            return 0.58 * _similarity(sig, row.semantic_hash) + 0.42 * lexical

        return sorted(rows, key=score, reverse=True)[: max(1, min(20, limit))]

    @staticmethod
    async def recent(chat_id: int, since: int, limit: int = 1200) -> list[ChatMemoryMessage]:
        async with session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ChatMemoryMessage)
                        .where(ChatMemoryMessage.chat_id == chat_id, ChatMemoryMessage.created_at >= since)
                        .order_by(ChatMemoryMessage.id.asc())
                        .limit(limit)
                    )
                ).all()
            )


class ProfileLearner:
    @staticmethod
    async def observe(message: Message) -> None:
        if not message.from_user or not message.text:
            return
        privacy = await PrivacyManager.get(message.from_user.id)
        if not (privacy.personal_memory and privacy.allow_profile_learning):
            return
        # Remember the Telegram display name and only explicit, low-risk preferences.
        await LongTermMemoryManager.remember(
            message.from_user.id, 0, "identity", "имя в Telegram", message.from_user.full_name[:180], 80
        )
        text = message.text.strip()[:1200]
        patterns = (
            (r"(?i)\bменя зовут\s+([^,.!?\n]{2,60})", "как меня зовут"),
            (r"(?i)\b(?:мне нравится|я люблю)\s+([^.!?\n]{2,120})", "мне нравится"),
            (r"(?i)\bмой любимый цвет\s*[-—:=]?\s*([^.!?\n]{2,60})", "любимый цвет"),
        )
        for pattern, key in patterns:
            match = re.search(pattern, text)
            if match:
                await LongTermMemoryManager.remember(
                    message.from_user.id, 0, "preference", key, match.group(1).strip(), 70
                )


class LongTermMemoryManager:
    @staticmethod
    async def remember(user_id: int, chat_id: int, kind: str, key: str, value: str, importance: int = 60) -> None:
        privacy = await PrivacyManager.get(user_id)
        if not privacy.personal_memory:
            return
        now = int(time.time())
        key = (key or kind)[:96]
        value = value.strip()[:3000]
        async with session_factory() as session:
            row = await session.scalar(
                select(LongTermMemory).where(
                    LongTermMemory.user_id == user_id,
                    LongTermMemory.chat_id == chat_id,
                    LongTermMemory.kind == kind,
                    LongTermMemory.key == key,
                ).limit(1)
            )
            if row:
                row.value = value
                row.importance = importance
                row.updated_at = now
            else:
                session.add(
                    LongTermMemory(
                        user_id=user_id,
                        chat_id=chat_id,
                        kind=kind[:32],
                        key=key,
                        value=value,
                        importance=max(1, min(100, importance)),
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.commit()

    @staticmethod
    async def list(user_id: int, chat_id: int, limit: int = 30) -> list[LongTermMemory]:
        async with session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(LongTermMemory)
                        .where(LongTermMemory.user_id == user_id, LongTermMemory.chat_id.in_([0, chat_id]))
                        .order_by(LongTermMemory.importance.desc(), LongTermMemory.updated_at.desc())
                        .limit(limit)
                    )
                ).all()
            )


@dataclass(slots=True)
class ModerationDecision:
    category: str = "ok"
    confidence: int = 0
    action: str = "none"
    explanation: str = ""


class AIModerator:
    @staticmethod
    async def inspect(message: Message) -> ModerationDecision | None:
        if not message.from_user or not message.text or message.chat.type == "private":
            return None
        cfg = await ChatMemoryManager.settings(message.chat.id)
        if cfg.moderator_mode == "off":
            return None
        text = message.text.strip()
        if not (_SUSPICIOUS_RE.search(text) or (_URL_RE.search(text) and len(text) < 500)):
            return None
        context = await ChatMemoryManager.recent(message.chat.id, int(time.time()) - 600, limit=25)
        context_text = "\n".join(f"{row.display_name}: {row.text[:300]}" for row in context[-12:])
        prompt = (
            "Classify the LAST Telegram message using conversation context. Return ONLY compact JSON with keys "
            "category(ok|insult|harassment|spam|raid|scam|suspicious_link), confidence(0-100), "
            "action(none|flag|delete), explanation(short Russian). Never flag friendly banter merely for profanity. "
            f"Strictness: {cfg.moderator_strictness}/5.\nCONTEXT:\n{context_text}\nLAST:\n{text[:1800]}"
        )
        try:
            raw = await ai.respond(
                prompt,
                user_id=0,
                chat_id=0,
                remember=False,
                instructions="You are a conservative safety classifier. Output JSON only.",
                preferred_order=("ollama",),
                temperature=0.1,
                max_tokens=220,
            )
            match = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(match.group(0) if match else raw)
            decision = ModerationDecision(
                str(data.get("category", "ok"))[:32],
                max(0, min(100, int(data.get("confidence", 0)))),
                str(data.get("action", "none"))[:16],
                str(data.get("explanation", ""))[:500],
            )
        except Exception:
            decision = ModerationDecision("suspicious", 55, "flag", "Сообщение выглядит рискованным, но AI-классификатор сейчас недоступен.")
        if decision.category == "ok" or decision.confidence < 50:
            return None
        if cfg.moderator_mode != "auto" or decision.confidence < 88:
            decision.action = "flag"
        async with session_factory() as session:
            session.add(
                AIModerationIncident(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    user_id=message.from_user.id,
                    category=decision.category,
                    confidence=decision.confidence,
                    action=decision.action,
                    explanation=decision.explanation,
                    created_at=int(time.time()),
                )
            )
            await session.commit()
        return decision


class AdminIntent:
    @staticmethod
    async def propose(chat_id: int, admin_id: int, request: str) -> PendingAdminAction:
        prompt = (
            "Convert this Telegram admin request into ONE safe settings proposal. Return ONLY JSON. Allowed keys: "
            "moderator_mode(off|assist|auto|null), moderator_strictness(1-5|null), memory_enabled(bool|null), "
            "retention_days(1-365|null), personality(normal|friendly|serious|humorous|rp|null), "
            "links_allowed(bool|null), human_summary(Russian string). Never propose irreversible punishments.\nREQUEST: "
            + request[:2500]
        )
        data: dict = {}
        try:
            raw = await ai.respond(prompt, user_id=admin_id, chat_id=chat_id, remember=False, temperature=0.1, max_tokens=300)
            match = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(match.group(0) if match else raw)
        except Exception:
            low = request.casefold()
            data = {"human_summary": "Изменение настроек Киры"}
            if "ссыл" in low:
                data["links_allowed"] = not any(x in low for x in ("запрет", "нельзя", "удал"))
            if "скам" in low or "модер" in low:
                data["moderator_mode"] = "auto" if "удал" in low else "assist"
            if "памят" in low:
                data["memory_enabled"] = not any(x in low for x in ("выкл", "не хран"))
            if "мат" in low or "цензур" in low:
                if any(x in low for x in ("без мата", "мат выкл", "цензур")):
                    data["speech_style"] = "clean"
                elif any(x in low for x in ("умерен", "иногда", "естествен")):
                    data["speech_style"] = "natural"
                else:
                    data["speech_style"] = "free"
        safe = {
            key: data.get(key)
            for key in ("moderator_mode", "moderator_strictness", "memory_enabled", "retention_days", "personality", "speech_style", "links_allowed")
            if data.get(key) is not None
        }
        summary = str(data.get("human_summary") or json.dumps(safe, ensure_ascii=False))[:1200]
        async with session_factory() as session:
            row = PendingAdminAction(
                chat_id=chat_id,
                admin_id=admin_id,
                action_json=json.dumps(safe, ensure_ascii=False),
                human_summary=summary,
                status="pending",
                created_at=int(time.time()),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row


class KiraNextMiddleware:
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            if event.from_user and event.text:
                nickname_match = re.match(
                    r"(?i)^\s*(?:кира\s*[,,:-]?\s*)?(?:называй|зови)\s+меня\s+(.{2,48}?)\s*[.!]?\s*$",
                    event.text,
                )
                if nickname_match:
                    try:
                        nickname = await NicknameManager.set(
                            event.from_user.id, event.chat.id, nickname_match.group(1)
                        )
                        await event.reply(
                            f"🦊 Запомнила. В этом чате буду звать тебя <b>{html.escape(nickname)}</b>. "
                            "Изменить можно через <code>/ник новый ник</code>."
                        )
                    except ValueError as exc:
                        await event.reply(f"Не получилось сохранить ник: {html.escape(str(exc))}")
                    return None
            try:
                await ChatMemoryManager.ingest(event)
                await ProfileLearner.observe(event)
            except Exception:
                log.exception("Kira memory ingest failed")
            try:
                decision = await AIModerator.inspect(event)
                if decision and event.chat.type != "private":
                    if decision.action == "delete":
                        try:
                            await event.delete()
                        except Exception:
                            pass
                        await event.answer(
                            f"🛡️ AI-модератор: сообщение удалено ({decision.category}, {decision.confidence}%).\n{decision.explanation}"
                        )
                        return None
                    await event.reply(
                        f"🛡️ Похоже на <b>{decision.category}</b> ({decision.confidence}%). {decision.explanation}\n"
                        "<i>Режим assist: решение остаётся за администраторами.</i>"
                    )
            except Exception:
                log.exception("AI moderation failed")
        return await handler(event, data)


kira_next_middleware = KiraNextMiddleware()
