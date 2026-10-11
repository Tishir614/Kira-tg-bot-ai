import logging
import random
import time
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import delete, event, func, inspect, or_, select, text, update
from sqlalchemy.engine import Connection, URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from bot.config import settings

from bot.sql.errors import (
    CharacterAlreadyMarried,
    CharacterNotMarried,
    MarryMe,
    MarryYourself,
    SelfNotHaveCharacter,
    UserNotHaveCharacter,
)
from bot.sql.orm_tables import (
    AniListMalCache,
    Character,
    Chat,
    Class,
    Mem,
    Race,
    RPTrigger,
    TableBase,
    User,
    UserNickname,
    Reminder,
    InventoryItem,
    Relationship,
    AssistantMemory,
    UserFact,
    ConversationSummary,
    ChatSettings,
    ChatMemorySettings,
    MatureProfile,
    MatureSession,
    Blacklist,
    AuditLog,
)

DEFAULT_RACES = [
    "Человек",
    "Эльф",
    "Дворф",
    "Орк",
    "Полуэльф",
    "Полуорк",
    "Гном",
    "Халфлинг",
    "Зверолюд",
    "Тёмный эльф",
    "Гоблин",
    "Кобольд",
    "Принцесса",
    "Робот",
    "Андроид",
    "Вампир",
    "Демон",
    "Ангел",
    "Неизвестна",
]

DEFAULT_CLASSES = [
    "Воин",
    "Маг",
    "Вор",
    "Жрец",
    "Паладин",
    "Рейнджер",
    "Бард",
    "Друид",
    "Монах",
    "Разбойник",
    "Колдун",
    "Чародей",
    "Варвар",
    "Лучник",
    "Некромант",
    "Лиса",
    "Дворянин",
    "Неизвестен",
]


BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = settings.data_dir
DATABASE_PATH = STATIC_DIR / "database.db"

STATIC_DIR.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    url=URL.create("sqlite+aiosqlite", database=str(DATABASE_PATH)),
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Improve SQLite concurrency and enforce relational integrity."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
    finally:
        cursor.close()


session_factory = async_sessionmaker(engine, expire_on_commit=False)
log = logging.getLogger(__name__)


class MemManager:
    @staticmethod
    async def add(chat_id: int, sticker_id: str) -> Optional[Mem]:
        added = await MemManager.add_many(chat_id, [sticker_id])
        return added[0] if added else None

    @staticmethod
    async def add_many(chat_id: int, sticker_ids: list[str]) -> list[Mem]:
        if not sticker_ids:
            return []

        unique_ids = list(dict.fromkeys(sticker_ids))

        async with session_factory() as session:
            existing_result = await session.execute(
                select(Mem.sticker_id).where(
                    Mem.chat_id == chat_id,
                    Mem.sticker_id.in_(unique_ids),
                )
            )
            existing_ids = set(existing_result.scalars().all())
            new_ids = [sid for sid in unique_ids if sid not in existing_ids]

            if new_ids:
                session.add_all(
                    [Mem(chat_id=chat_id, sticker_id=sid) for sid in new_ids]
                )
                await session.commit()

            result = await session.execute(
                select(Mem).where(
                    Mem.chat_id == chat_id,
                    Mem.sticker_id.in_(unique_ids),
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def remove(chat_id: int, mem_id: int) -> bool:
        async with session_factory() as session:
            result = await session.execute(
                select(Mem).where(
                    Mem.id == mem_id,
                    Mem.chat_id == chat_id,
                )
            )
            mem = result.scalar_one_or_none()
            if not mem:
                return False
            await session.delete(mem)
            await session.commit()
            return True

    @staticmethod
    async def list(chat_id: int) -> list[Mem]:
        async with session_factory() as session:
            result = await session.execute(select(Mem).where(Mem.chat_id == chat_id))
            return list(result.scalars().all())

    @staticmethod
    async def get_random_id(chat_id: int) -> Optional[str]:
        async with session_factory() as session:
            result = await session.execute(
                select(Mem.sticker_id)
                .where(Mem.chat_id == chat_id)
                .order_by(func.random())
                .limit(1)
            )
            return result.scalar_one_or_none()


class AniListMalCacheManager:
    @staticmethod
    async def get_mal_id(anilist_id: int) -> Optional[int]:
        async with session_factory() as session:
            statement = select(AniListMalCache.mal_id).where(
                AniListMalCache.anilist_id == anilist_id
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    @staticmethod
    async def upsert(anilist_id: int, mal_id: int) -> None:
        async with session_factory() as session:
            mapping = await session.get(AniListMalCache, anilist_id)
            if mapping is None:
                session.add(AniListMalCache(anilist_id=anilist_id, mal_id=mal_id))
            else:
                mapping.mal_id = mal_id
            await session.commit()


class UserManager:
    @staticmethod
    async def get(user_id: int) -> Optional[User]:
        async with session_factory() as session:
            stmt = select(User).where(User.user_id == user_id).exists()
            exists = await session.execute(select(stmt))
            if exists.scalar():
                user = await session.get(
                    User, user_id, options=[selectinload(User.character)]
                )
                return user
            new_user = User(user_id=user_id)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user, ["character", "sudo"])
            return new_user

    @staticmethod
    async def promote(user_id: int):
        async with session_factory() as session:
            stmt = update(User).where(User.user_id == user_id).values(sudo=True)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def demote(user_id: int):
        async with session_factory() as session:
            stmt = update(User).where(User.user_id == user_id).values(sudo=False)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        async with session_factory() as session:
            stmt = select(User.sudo).where(User.user_id == user_id)
            result = await session.execute(stmt)
            return bool(result.scalar_one_or_none())

    @staticmethod
    async def set_adult_confirmed(user_id: int, confirmed: bool) -> None:
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.adult_confirmed = bool(confirmed)
            await session.commit()

    @staticmethod
    async def is_adult_confirmed(user_id: int) -> bool:
        async with session_factory() as session:
            value = await session.scalar(select(User.adult_confirmed).where(User.user_id == user_id))
            return bool(value)

    @staticmethod
    async def set_bio(user_id: int, bio: str) -> str:
        value = (bio or "").replace("\x00", " ").strip()[:180]
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.bio = value
            await session.commit()
            return value

    @staticmethod
    async def update_masturbate_stats(
        user_id: int,
        *,
        penis_len: float,
        cooldown_until: int,
        effect: str = "",
        effect_until: int = 0,
    ) -> None:
        async with session_factory() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    penis_len=penis_len,
                    masturbate_cooldown_until=cooldown_until,
                    active_effect=effect[:64],
                    active_effect_until=effect_until,
                )
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def get_top_penis(limit: int = 10) -> list[User]:
        async with session_factory() as session:
            result = await session.execute(
                select(User)
                .where(User.penis_len > 0)
                .order_by(User.penis_len.desc(), User.user_id.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_alcohol_stats(
        user_id: int,
        *,
        alcohol_score: float,
        cooldown_until: int,
        effect: str = "",
        effect_until: int = 0,
    ) -> None:
        async with session_factory() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    alcohol_score=alcohol_score,
                    alcohol_cooldown_until=cooldown_until,
                    active_effect=effect[:64],
                    active_effect_until=effect_until,
                )
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def get_top_alcohol(limit: int = 10) -> list[User]:
        async with session_factory() as session:
            result = await session.execute(
                select(User)
                .where(User.alcohol_score > 0)
                .order_by(User.alcohol_score.desc(), User.user_id.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_tail_stats(
        user_id: int,
        *,
        tail_fluff: float,
        cooldown_until: int,
    ) -> None:
        async with session_factory() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    tail_fluff=tail_fluff,
                    tail_cooldown_until=cooldown_until,
                )
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def get_top_tails(limit: int = 10) -> list[User]:
        async with session_factory() as session:
            result = await session.execute(
                select(User)
                .where(User.tail_fluff > 0)
                .order_by(User.tail_fluff.desc(), User.user_id.asc())
                .limit(limit)
            )
            return list(result.scalars().all())


class ProfileCustomizationManager:
    """Persistent profile cosmetics and user-selected gender.

    Colors are real hex colors inside Kira Mini App. Telegram message text itself
    cannot be recolored, therefore normal chat output uses a matching color badge.
    """

    GENDERS = {
        "male": "мужской",
        "female": "женский",
        "other": "другое",
        "unspecified": "не указан",
    }
    GENDER_ALIASES = {
        "м": "male", "муж": "male", "мужской": "male", "male": "male",
        "ж": "female", "жен": "female", "женский": "female", "female": "female",
        "другое": "other", "другой": "other", "other": "other",
        "не указывать": "unspecified", "не_указывать": "unspecified",
        "скрыть": "unspecified", "нет": "unspecified", "off": "unspecified",
    }
    THEMES = {"violet", "midnight", "rose", "emerald", "amber"}

    @staticmethod
    async def get(user_id: int) -> User:
        return await UserManager.get(user_id)

    @staticmethod
    async def set_gender(user_id: int, value: str) -> str:
        normalized = ProfileCustomizationManager.GENDER_ALIASES.get(" ".join((value or "").casefold().split()))
        if normalized is None:
            raise ValueError("Пол: мужской / женский / другое / не указывать.")
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.gender = normalized
            await session.commit()
        return normalized

    @staticmethod
    async def set_color(user_id: int, value: str) -> str:
        value = (value or "").strip().upper()
        if not value.startswith("#"):
            value = "#" + value
        if len(value) != 7 or any(ch not in "#0123456789ABCDEF" for ch in value):
            raise ValueError("Цвет должен быть HEX, например #FF66CC.")
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.profile_color = value
            await session.commit()
        return value

    @staticmethod
    async def set_title(user_id: int, value: str) -> str:
        value = " ".join((value or "").replace("\x00", " " ).split()).strip()[:48]
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.profile_title = value
            await session.commit()
        return value

    @staticmethod
    async def set_badge(user_id: int, value: str) -> str:
        value = "".join((value or "").strip().split())[:16] or "🦊"
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.profile_badge = value
            await session.commit()
        return value

    @staticmethod
    async def set_theme(user_id: int, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ProfileCustomizationManager.THEMES:
            raise ValueError("Тема: violet / midnight / rose / emerald / amber.")
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
            user.profile_theme = value
            await session.commit()
        return value

    @staticmethod
    def color_badge(hex_color: str | None) -> str:
        value = (hex_color or "#E8BDFF").upper()
        try:
            r, g, b = int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
        except (ValueError, IndexError):
            return "🟪"
        choices = [
            ((255, 80, 100), "🟥"), ((255, 160, 40), "🟧"), ((245, 220, 50), "🟨"),
            ((70, 190, 100), "🟩"), ((70, 140, 230), "🟦"), ((160, 90, 220), "🟪"),
            ((245, 245, 245), "⬜"), ((45, 45, 45), "⬛"),
        ]
        return min(choices, key=lambda item: (r-item[0][0])**2 + (g-item[0][1])**2 + (b-item[0][2])**2)[1]


class ChatManager:
    @staticmethod
    async def get(chat_id: int) -> Optional[Chat]:
        async with session_factory() as session:
            result = await session.execute(
                select(Chat).where(
                    or_(Chat.chat_id == chat_id, Chat.admin_chat_id == chat_id)
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_all() -> list[Chat]:
        async with session_factory() as session:
            result = await session.execute(select(Chat))
            return list(result.scalars().all())

    @staticmethod
    async def upsert(chat_id: int, admin_chat: Optional[int] = None):
        async with session_factory() as session:
            chat = await session.get(Chat, chat_id)

            if not chat:
                chat = Chat(chat_id=chat_id)
                session.add(chat)

            chat.admin_chat_id = admin_chat
            if not int(chat.created_at or 0):
                chat.created_at = int(time.time())

            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise


class CharacterManager:
    @staticmethod
    async def upsert(user_id: int, character: Character):
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()

            db_char = await session.scalar(
                select(Character).where(Character.user_id == user_id)
            )
            if db_char is None:
                db_char = Character(user_id=user_id)
                session.add(db_char)

            protected_fields = {"id", "married_id", "user_id"}

            for key, value in character.__dict__.items():
                if key not in protected_fields and not key.startswith("_"):
                    setattr(db_char, key, value)

            await session.commit()

    @staticmethod
    async def get(user_id: int) -> Optional[Character]:
        async with session_factory() as session:
            result = await session.execute(
                select(Character)
                .options(selectinload(Character.married))
                .where(Character.user_id == user_id)
            )

            return result.scalar_one_or_none()

    @staticmethod
    async def premarry(user_id: int, marry_id: int, bot_id: int):
        character = await CharacterManager.get(user_id)
        marry_character = await CharacterManager.get(marry_id)
        if marry_id == bot_id:
            raise MarryMe()
        if not character:
            raise SelfNotHaveCharacter
        elif not marry_character:
            raise UserNotHaveCharacter

        if character.id == marry_character.id:
            raise MarryYourself()

        if character.married_id or marry_character.married_id:
            raise CharacterAlreadyMarried()

    @staticmethod
    async def marry(user_id: int, marry_id: int) -> bool:
        async with session_factory() as session:
            character = await session.scalar(
                select(Character).where(Character.user_id == user_id)
            )
            marry_character = await session.scalar(
                select(Character).where(Character.user_id == marry_id)
            )

            if character is None:
                raise SelfNotHaveCharacter()
            if marry_character is None:
                raise UserNotHaveCharacter()
            if character.id == marry_character.id:
                raise MarryYourself()
            # Повторная проверка нужна при нажатии на старую callback-кнопку.
            if character.married_id or marry_character.married_id:
                raise CharacterAlreadyMarried()

            try:
                character.married_id = marry_character.id
                marry_character.married_id = character.id
                await session.commit()
                return True
            except Exception:
                await session.rollback()
                raise

    @staticmethod
    async def preunmarry(user_id: int):
        async with session_factory() as session:
            character = await session.scalar(
                select(Character)
                .where(Character.user_id == user_id)
                .options(selectinload(Character.married))
            )
            if not character or not character.married_id or not character.married:
                raise CharacterNotMarried()

    @staticmethod
    async def unmarry(user_id: int):
        async with session_factory() as session:
            character = await session.scalar(
                select(Character).where(Character.user_id == user_id)
            )
            if not character or not character.married_id:
                raise CharacterNotMarried()

            marry_character = await session.get(Character, character.married_id)

            try:
                # Не разрываем чужую новую связь при повреждённой/старой записи.
                if marry_character and marry_character.married_id == character.id:
                    marry_character.married_id = None
                character.married_id = None
                await session.commit()
                return True
            except Exception:
                await session.rollback()
                raise

    @staticmethod
    async def is_married(user_id: int) -> bool:
        character = await CharacterManager.get(user_id)
        return bool(character and character.married_id)


class NicknameManager:
    """Persistent, privacy-friendly nicknames used by Kira and RP."""

    @staticmethod
    def clean(value: str) -> str:
        value = " ".join((value or "").replace("\x00", " ").split()).strip()
        value = "".join(ch for ch in value if ch.isprintable())
        return value[:32].strip()

    @staticmethod
    async def get(user_id: int, chat_id: int = 0) -> Optional[str]:
        async with session_factory() as session:
            if chat_id:
                row = await session.scalar(
                    select(UserNickname).where(
                        UserNickname.user_id == user_id,
                        UserNickname.chat_id == chat_id,
                    ).limit(1)
                )
                if row and row.nickname:
                    return row.nickname
            row = await session.scalar(
                select(UserNickname).where(
                    UserNickname.user_id == user_id,
                    UserNickname.chat_id == 0,
                ).limit(1)
            )
            return row.nickname if row and row.nickname else None

    @staticmethod
    async def get_scoped(user_id: int, chat_id: int) -> tuple[Optional[str], Optional[str]]:
        async with session_factory() as session:
            rows = list((await session.scalars(
                select(UserNickname).where(
                    UserNickname.user_id == user_id,
                    UserNickname.chat_id.in_([0, chat_id]),
                )
            )).all())
        current = next((r.nickname for r in rows if r.chat_id == chat_id), None)
        global_name = next((r.nickname for r in rows if r.chat_id == 0), None)
        return current, global_name

    @staticmethod
    async def set(user_id: int, chat_id: int, nickname: str) -> str:
        nickname = NicknameManager.clean(nickname)
        if not 2 <= len(nickname) <= 32:
            raise ValueError("Ник должен содержать от 2 до 32 символов.")
        if nickname.startswith("/") or "<" in nickname or ">" in nickname:
            raise ValueError("В нике нельзя использовать команды или угловые скобки.")
        now = int(time.time())
        async with session_factory() as session:
            row = await session.scalar(
                select(UserNickname).where(
                    UserNickname.user_id == user_id,
                    UserNickname.chat_id == chat_id,
                ).limit(1)
            )
            if row is None:
                row = UserNickname(user_id=user_id, chat_id=chat_id, nickname=nickname, updated_at=now)
                session.add(row)
            else:
                row.nickname = nickname
                row.updated_at = now
            await session.commit()
        return nickname

    @staticmethod
    async def delete(user_id: int, chat_id: int) -> bool:
        async with session_factory() as session:
            result = await session.execute(
                delete(UserNickname).where(
                    UserNickname.user_id == user_id,
                    UserNickname.chat_id == chat_id,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def delete_all(user_id: int) -> int:
        async with session_factory() as session:
            result = await session.execute(delete(UserNickname).where(UserNickname.user_id == user_id))
            await session.commit()
            return int(result.rowcount or 0)


class RaceManager:
    @staticmethod
    async def get_all() -> list[Race]:
        async with session_factory() as session:
            races = await session.scalars(select(Race))
            return list(races.all())

    @staticmethod
    async def get_by_id(race_id: int) -> Race:
        async with session_factory() as session:
            stmt = select(Race).where(Race.id == race_id)
            races = await session.scalars(stmt)
            return races.first()

    @staticmethod
    async def get_by_name(name: str) -> Optional[Race]:
        async with session_factory() as session:
            stmt = select(Race).where(Race.name == name)
            races = await session.scalars(stmt)
            return races.first()

    @staticmethod
    async def new(race: Race) -> bool:
        async with session_factory() as session:
            exists = await session.scalar(
                select(select(Race).where(Race.name == race.name).exists())
            )
            if exists:
                return False
            session.add(Race(name=race.name))
            await session.commit()
            return True

    @staticmethod
    async def delete(race: Race) -> bool:
        async with session_factory() as session:
            db_race = None
            if race.id is not None:
                db_race = await session.get(Race, race.id)
            if db_race is None:
                db_race = await session.scalar(
                    select(Race).where(Race.name == race.name)
                )

            if not db_race:
                return False
            await session.delete(db_race)
            await session.commit()
            return True


class ClassManager:
    @staticmethod
    async def get_all() -> list[Class]:
        async with session_factory() as session:
            classes = await session.scalars(select(Class))
            return list(classes.all())

    @staticmethod
    async def get_by_id(class_id: int) -> Class:
        async with session_factory() as session:
            stmt = select(Class).where(Class.id == class_id)
            classes = await session.scalars(stmt)
            return classes.first()

    @staticmethod
    async def get_by_name(name: str) -> Optional[Class]:
        async with session_factory() as session:
            stmt = select(Class).where(Class.name == name)
            classes = await session.scalars(stmt)
            return classes.first()

    @staticmethod
    async def new(cl: Class) -> bool:
        async with session_factory() as session:
            exists = await session.scalar(
                select(select(Class).where(Class.name == cl.name).exists())
            )
            if exists:
                return False
            session.add(Class(name=cl.name))
            await session.commit()
            return True

    @staticmethod
    async def delete(cl: Class) -> bool:
        async with session_factory() as session:
            db_class = None
            if cl.id is not None:
                db_class = await session.get(Class, cl.id)
            if db_class is None:
                db_class = await session.scalar(
                    select(Class).where(Class.name == cl.name)
                )

            if not db_class:
                return False
            await session.delete(db_class)
            await session.commit()
            return True


class RPManager:
    DEFAULT_RP = [
        RPTrigger(trigger="поцеловать", answer="{u1} поцеловал(а) {u2}"),
        RPTrigger(trigger="обнять", answer="{u1} обнял(а) {u2}"),
        RPTrigger(trigger="чмок", answer="{u1} чмокнул(а) {u2}"),
        RPTrigger(trigger="убить", answer="{u1} убил(а) {u2}"),
        RPTrigger(trigger="трахнуть", answer="{u1} трахнул(а) {u2}"),
        RPTrigger(trigger="пожать", answer="{u1} пожал(а) руку {u2}"),
        RPTrigger(trigger="ударить", answer="{u1} ударил(а) {u2}"),
        RPTrigger(trigger="отсосать", answer="{u1} отсосал(а) {u2}"),
        RPTrigger(trigger="улыбнуться", answer="{u1} улыбнулся(ась)"),
        RPTrigger(trigger="заплакать", answer="{u1} заплакал(а)"),
        RPTrigger(trigger="расстроиться", answer="{u1} расстроился(ась)"),
        RPTrigger(trigger="смеяться", answer="{u1} смеется"),
        RPTrigger(trigger="удивиться", answer="{u1} удивился(ась)"),
        RPTrigger(trigger="помахать головой", answer="{u1} помахал(а) головой"),
        RPTrigger(trigger="разозлиться", answer="{u1} разозлился"),
    ]

    def __init__(self):
        # Ключ включает chat_id, иначе одинаковые триггеры разных групп
        # перезаписывали друг друга в памяти.
        self.objects: Dict[tuple[int, str], RPTrigger] = {}
        self.triggers: set[str] = set()

    @staticmethod
    def _normalize(trigger: str) -> str:
        return trigger.strip().lower()

    @staticmethod
    async def get(trigger: str) -> Optional[RPTrigger]:
        """Возвращает глобальный триггер для обратной совместимости."""
        normalized = RPManager._normalize(trigger)
        async with session_factory() as session:
            return await session.scalar(
                select(RPTrigger)
                .where(RPTrigger.trigger == normalized, RPTrigger.chat_id == 0)
                .order_by(RPTrigger.id.desc())
                .limit(1)
            )

    @staticmethod
    async def get_for_chat(trigger: str, chat_id: int) -> Optional[RPTrigger]:
        normalized = RPManager._normalize(trigger)
        async with session_factory() as session:
            return await session.scalar(
                select(RPTrigger)
                .where(
                    RPTrigger.trigger == normalized,
                    RPTrigger.chat_id == chat_id,
                )
                .order_by(RPTrigger.id.desc())
                .limit(1)
            )

    def get_by_chat_id(self, chat_id: int) -> Optional[list[RPTrigger]]:
        # Сначала глобальные команды, затем локальные переопределяют одноимённые.
        effective: dict[str, RPTrigger] = {
            trigger: obj
            for (scope, trigger), obj in self.objects.items()
            if scope == 0
        }
        effective.update({
            trigger: obj
            for (scope, trigger), obj in self.objects.items()
            if scope == chat_id
        })
        result = sorted(effective.values(), key=lambda item: item.trigger)
        return result or None

    async def new(self, trigger: RPTrigger):
        normalized = self._normalize(trigger.trigger)
        trigger.trigger = normalized
        trigger.type = "action" if "{u2}" in trigger.answer else "emotion"

        async with session_factory() as session:
            existing_rows = list((await session.scalars(
                select(RPTrigger)
                .where(
                    RPTrigger.trigger == normalized,
                    RPTrigger.chat_id == trigger.chat_id,
                )
                .order_by(RPTrigger.id.asc())
            )).all())

            if existing_rows:
                existing = existing_rows[0]
                existing.answer = trigger.answer
                existing.type = trigger.type
                # Старые версии могли создать дубликаты. Удаляем их при обновлении.
                for duplicate in existing_rows[1:]:
                    await session.delete(duplicate)
            else:
                session.add(trigger)

            await session.commit()

        await self.load_all_triggers()

    async def delete(self, trigger: RPTrigger):
        normalized = self._normalize(trigger.trigger)
        async with session_factory() as session:
            rows = list((await session.scalars(
                select(RPTrigger).where(
                    RPTrigger.trigger == normalized,
                    RPTrigger.chat_id == trigger.chat_id,
                )
            )).all())
            for row in rows:
                await session.delete(row)
            await session.commit()
        await self.load_all_triggers()

    async def load_all_triggers(self):
        async with session_factory() as session:
            rp_triggers = (await session.execute(
                select(RPTrigger).order_by(RPTrigger.id.asc())
            )).scalars().all()

        self.objects = {}
        self.triggers = set()
        for rp_trigger in rp_triggers:
            key = self._normalize(rp_trigger.trigger)
            rp_trigger.trigger = key
            self.objects[(rp_trigger.chat_id, key)] = rp_trigger
            self.triggers.add(key)

    def check(self, text: str, chat_id: int) -> Optional[RPTrigger]:
        key = self._normalize(text)
        return self.objects.get((chat_id, key)) or self.objects.get((0, key))

    def match(self, text: str, chat_id: int) -> tuple[Optional[RPTrigger], str | None]:
        """Находит RP-команду в начале сообщения и возвращает её аргумент."""
        normalized_text = self._normalize(text)
        available = self.get_by_chat_id(chat_id) or []

        # Длинные триггеры проверяем первыми: "помахать головой" не должен
        # быть случайно перехвачен коротким пересекающимся триггером.
        for trigger in sorted(available, key=lambda item: len(item.trigger), reverse=True):
            key = self._normalize(trigger.trigger)
            if normalized_text == key:
                return trigger, None
            prefix = f"{key} "
            if normalized_text.startswith(prefix):
                argument = text.strip()[len(key):].strip()
                return trigger, argument or None
        return None, None

    async def load_default(self):
        async with session_factory() as session:
            changed = False
            for rp in self.DEFAULT_RP:
                normalized = self._normalize(rp.trigger)
                exists = await session.scalar(
                    select(
                        select(RPTrigger)
                        .where(
                            RPTrigger.trigger == normalized,
                            RPTrigger.chat_id == 0,
                        )
                        .exists()
                    )
                )
                if not exists:
                    session.add(RPTrigger(
                        trigger=normalized,
                        answer=rp.answer,
                        type="action" if "{u2}" in rp.answer else "emotion",
                        chat_id=0,
                    ))
                    changed = True
            if changed:
                await session.commit()

        await self.load_all_triggers()


class EconomyManager:
    @staticmethod
    async def add_xp(user_id: int, amount: int = 5) -> tuple[int, int, bool]:
        amount = max(0, min(int(amount), 500))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            old_level = max(1, int(user.level or 1))
            user.xp = max(0, int(user.xp or 0)) + amount
            level = old_level
            # Кумулятивная шкала: следующий уровень требует 100 * текущий уровень XP.
            while user.xp >= 100 * level:
                user.xp -= 100 * level
                level += 1
                user.coins = int(user.coins or 0) + 25 * level
            user.level = level
            await session.commit()
            return user.xp, level, level > old_level

    @staticmethod
    async def daily(user_id: int, now: int) -> tuple[bool, int, int, int]:
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            last = int(user.last_daily_at or 0)
            cooldown = 24 * 60 * 60
            if last and now - last < cooldown:
                return False, 0, int(user.daily_streak or 0), cooldown - (now - last)
            streak = int(user.daily_streak or 0) + 1 if last and now - last <= 48 * 60 * 60 else 1
            reward = 100 + min(streak, 30) * 15
            user.daily_streak = streak
            user.last_daily_at = now
            user.coins = int(user.coins or 0) + reward
            await session.commit()
            return True, reward, streak, 0

    @staticmethod
    async def work(user_id: int, now: int) -> tuple[bool, int, int, int, int, bool]:
        """Hourly local-economy job. Returns ok, coins, xp, remaining, level, level_up."""
        cooldown = 60 * 60
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            last = int(user.last_work_at or 0)
            if last and now - last < cooldown:
                remaining = cooldown - (now - last)
                level = int(user.level or 1)
                await session.rollback()
                return False, 0, 0, remaining, level, False

            level = max(1, int(user.level or 1))
            old_level = level
            reward = random.randint(45, 95) + min(60, level * 3)
            xp_gain = random.randint(8, 18)
            user.last_work_at = now
            user.coins = max(0, int(user.coins or 0) + reward)
            user.xp = max(0, int(user.xp or 0) + xp_gain)
            while user.xp >= 100 * level:
                user.xp -= 100 * level
                level += 1
                user.coins = int(user.coins or 0) + 25 * level
            user.level = level
            await session.commit()
            return True, reward, xp_gain, 0, level, level > old_level

    @staticmethod
    async def transfer_coins(from_user: int, to_user: int, amount: int) -> tuple[bool, int, int]:
        if from_user == to_user:
            return False, 0, 0
        amount = max(1, min(int(amount), 100_000))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            sender = await session.get(User, from_user)
            if sender is None:
                sender = User(user_id=from_user)
                session.add(sender)
                await session.flush()
            receiver = await session.get(User, to_user)
            if receiver is None:
                receiver = User(user_id=to_user)
                session.add(receiver)
                await session.flush()
            if int(sender.coins or 0) < amount:
                sender_balance = int(sender.coins or 0)
                receiver_balance = int(receiver.coins or 0)
                await session.rollback()
                return False, sender_balance, receiver_balance
            sender.coins = int(sender.coins or 0) - amount
            receiver.coins = int(receiver.coins or 0) + amount
            await session.commit()
            return True, int(sender.coins or 0), int(receiver.coins or 0)

    @staticmethod
    async def balances(user_ids: list[int]) -> dict[int, int]:
        ids = list(dict.fromkeys(int(x) for x in user_ids if int(x) > 0))[:100]
        if not ids:
            return {}
        async with session_factory() as session:
            rows = await session.execute(select(User.user_id, User.coins).where(User.user_id.in_(ids)))
            return {int(uid): int(coins or 0) for uid, coins in rows.all()}

    @staticmethod
    async def spend(user_id: int, amount: int) -> bool:
        amount = max(0, int(amount))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            if int(user.coins or 0) < amount:
                return False
            user.coins = int(user.coins or 0) - amount
            await session.commit()
            return True

    @staticmethod
    async def add_coins(user_id: int, amount: int) -> int:
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            user.coins = max(0, int(user.coins or 0) + int(amount))
            await session.commit()
            return user.coins

    @staticmethod
    async def purchase_item(user_id: int, item_key: str, price: int, now: int) -> bool:
        """Atomically charge coins and place an item in the inventory."""
        price = max(0, int(price))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            if int(user.coins or 0) < price:
                await session.rollback()
                return False

            item = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == user_id,
                InventoryItem.item_key == item_key,
            ))
            user.coins = int(user.coins or 0) - price
            if item:
                item.quantity = int(item.quantity or 0) + 1
            else:
                session.add(InventoryItem(
                    user_id=user_id,
                    item_key=item_key,
                    quantity=1,
                    acquired_at=now,
                ))
            await session.commit()
            return True

    @staticmethod
    async def settle_wager(user_id: int, stake: int, payout: int) -> bool:
        """Apply a virtual-currency wager in one SQLite write transaction."""
        stake = max(0, int(stake))
        payout = max(0, int(payout))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            if int(user.coins or 0) < stake:
                await session.rollback()
                return False
            user.coins = max(0, int(user.coins or 0) - stake + payout)
            await session.commit()
            return True

    @staticmethod
    async def set_birthday(user_id: int, day: int, month: int) -> None:
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            user = await session.get(User, user_id)
            if user is None:
                user = User(user_id=user_id)
                session.add(user)
                await session.flush()
            user.birthday_day = day
            user.birthday_month = month
            await session.commit()


class InventoryManager:
    @staticmethod
    async def add(user_id: int, item_key: str, quantity: int = 1, now: int = 0) -> None:
        quantity = max(1, int(quantity))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            item = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == user_id,
                InventoryItem.item_key == item_key,
            ))
            if item:
                item.quantity += quantity
            else:
                session.add(InventoryItem(
                    user_id=user_id,
                    item_key=item_key,
                    quantity=quantity,
                    acquired_at=now,
                ))
            await session.commit()

    @staticmethod
    async def remove(user_id: int, item_key: str, quantity: int = 1) -> bool:
        quantity = max(1, int(quantity))
        async with session_factory() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            item = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == user_id,
                InventoryItem.item_key == item_key,
            ))
            if not item or item.quantity < quantity:
                return False
            item.quantity -= quantity
            if item.quantity <= 0:
                await session.delete(item)
            await session.commit()
            return True

    @staticmethod
    async def list(user_id: int) -> list[InventoryItem]:
        async with session_factory() as session:
            result = await session.scalars(
                select(InventoryItem)
                .where(InventoryItem.user_id == user_id)
                .order_by(InventoryItem.item_key.asc())
            )
            return list(result.all())

    @staticmethod
    async def has(user_id: int, item_key: str, quantity: int = 1) -> bool:
        async with session_factory() as session:
            item = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == user_id,
                InventoryItem.item_key == item_key,
            ))
            return bool(item and int(item.quantity or 0) >= max(1, int(quantity)))

    @staticmethod
    async def transfer(from_user: int, to_user: int, item_key: str, quantity: int, now: int) -> bool:
        if from_user == to_user:
            return False
        quantity = max(1, int(quantity))
        async with session_factory() as session:
            # One write transaction prevents item loss/duplication if the process
            # crashes between remove() and add().
            await session.execute(text("BEGIN IMMEDIATE"))
            source = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == from_user,
                InventoryItem.item_key == item_key,
            ))
            if not source or int(source.quantity or 0) < quantity:
                await session.rollback()
                return False

            target = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == to_user,
                InventoryItem.item_key == item_key,
            ))
            source.quantity -= quantity
            if source.quantity <= 0:
                await session.delete(source)
            if target:
                target.quantity += quantity
            else:
                session.add(InventoryItem(
                    user_id=to_user,
                    item_key=item_key,
                    quantity=quantity,
                    acquired_at=now,
                ))
            await session.commit()
            return True


class RelationshipManager:
    @staticmethod
    async def bump(user_id: int, target_user_id: int, *, friendship: int = 1, reputation: int = 0, now: int = 0) -> None:
        if user_id == target_user_id:
            return
        async with session_factory() as session:
            row = await session.scalar(select(Relationship).where(
                Relationship.user_id == user_id,
                Relationship.target_user_id == target_user_id,
            ))
            if row is None:
                row = Relationship(
                    user_id=user_id,
                    target_user_id=target_user_id,
                    friendship=0,
                    reputation=0,
                    interactions=0,
                    updated_at=now,
                )
                session.add(row)
            row.friendship = max(-1000, min(1000, int(row.friendship or 0) + friendship))
            row.reputation = max(-1000, min(1000, int(row.reputation or 0) + reputation))
            row.interactions = int(row.interactions or 0) + 1
            row.updated_at = now
            await session.commit()

    @staticmethod
    async def get(user_id: int, target_user_id: int) -> Optional[Relationship]:
        async with session_factory() as session:
            return await session.scalar(select(Relationship).where(
                Relationship.user_id == user_id,
                Relationship.target_user_id == target_user_id,
            ))


class ReminderManager:
    @staticmethod
    async def create(user_id: int, chat_id: int, text_value: str, due_at: int, repeat_seconds: int | None, created_at: int) -> Reminder:
        async with session_factory() as session:
            row = Reminder(
                user_id=user_id,
                chat_id=chat_id,
                text=text_value,
                due_at=due_at,
                repeat_seconds=repeat_seconds,
                created_at=created_at,
                enabled=True,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def due(now: int, limit: int = 100) -> list[Reminder]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(Reminder)
                .where(Reminder.enabled.is_(True), Reminder.due_at <= now)
                .order_by(Reminder.due_at.asc())
                .limit(limit)
            )
            return list(rows.all())

    @staticmethod
    async def complete(reminder_id: int, now: int) -> None:
        async with session_factory() as session:
            row = await session.get(Reminder, reminder_id)
            if not row:
                return
            if row.repeat_seconds and row.repeat_seconds > 0:
                row.due_at = max(row.due_at + row.repeat_seconds, now + 1)
            else:
                row.enabled = False
            await session.commit()

    @staticmethod
    async def list(user_id: int) -> list[Reminder]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(Reminder)
                .where(Reminder.user_id == user_id, Reminder.enabled.is_(True))
                .order_by(Reminder.due_at.asc())
            )
            return list(rows.all())

    @staticmethod
    async def delete(reminder_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            row = await session.scalar(select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
            ))
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True

    @staticmethod
    async def defer(reminder_id: int, due_at: int) -> None:
        async with session_factory() as session:
            row = await session.get(Reminder, reminder_id)
            if not row or not row.enabled:
                return
            row.due_at = max(int(due_at), int(time.time()) + 1)
            await session.commit()


class AssistantMemoryManager:
    @staticmethod
    async def add(user_id: int, chat_id: int, role: str, content: str, created_at: int) -> list[tuple[str, str]]:
        """Store a turn; return the (role, content) pairs trimmed off the end of the window."""
        content = content[:12000]
        async with session_factory() as session:
            last = await session.scalar(
                select(AssistantMemory)
                .where(AssistantMemory.user_id == user_id, AssistantMemory.chat_id == chat_id)
                .order_by(AssistantMemory.id.desc())
                .limit(1)
            )
            if last is not None and last.role == role[:16] and last.content == content:
                return []  # reconnect/retry paths must not store the same turn twice
            session.add(AssistantMemory(
                user_id=user_id,
                chat_id=chat_id,
                role=role[:16],
                content=content,
                created_at=created_at,
            ))
            await session.commit()
            # Держим только последние 24 сообщения на пару user/chat.
            old = list((await session.execute(
                select(AssistantMemory.id, AssistantMemory.role, AssistantMemory.content)
                .where(AssistantMemory.user_id == user_id, AssistantMemory.chat_id == chat_id)
                .order_by(AssistantMemory.id.desc())
                .offset(24)
            )).all())
            if old:
                await session.execute(delete(AssistantMemory).where(AssistantMemory.id.in_([r[0] for r in old])))
                await session.commit()
            return [(r[1], r[2]) for r in reversed(old)]

    @staticmethod
    async def context(user_id: int, chat_id: int, limit: int = 12) -> list[AssistantMemory]:
        async with session_factory() as session:
            rows = list((await session.scalars(
                select(AssistantMemory)
                .where(AssistantMemory.user_id == user_id, AssistantMemory.chat_id == chat_id)
                .order_by(AssistantMemory.id.desc())
                .limit(limit)
            )).all())
            rows.reverse()
            return rows

    @staticmethod
    async def clear(user_id: int, chat_id: int) -> None:
        async with session_factory() as session:
            await session.execute(delete(AssistantMemory).where(
                AssistantMemory.user_id == user_id,
                AssistantMemory.chat_id == chat_id,
            ))
            await session.commit()


class ConversationSummaryManager:
    @staticmethod
    async def get(user_id: int, chat_id: int) -> str:
        async with session_factory() as session:
            row = await session.scalar(select(ConversationSummary).where(
                ConversationSummary.user_id == user_id, ConversationSummary.chat_id == chat_id))
            return row.text if row else ""

    @staticmethod
    async def set(user_id: int, chat_id: int, text: str) -> None:
        async with session_factory() as session:
            row = await session.scalar(select(ConversationSummary).where(
                ConversationSummary.user_id == user_id, ConversationSummary.chat_id == chat_id))
            if row is None:
                row = ConversationSummary(user_id=user_id, chat_id=chat_id)
                session.add(row)
            row.text = text[:3000]
            row.updated_at = int(time.time())
            await session.commit()

    @staticmethod
    async def clear(user_id: int, chat_id: int) -> None:
        async with session_factory() as session:
            await session.execute(delete(ConversationSummary).where(
                ConversationSummary.user_id == user_id, ConversationSummary.chat_id == chat_id))
            await session.commit()


class UserFactManager:
    """Long-term facts a user told Kira about themselves (see bot/user_facts.py)."""

    @staticmethod
    async def remember(user_id: int, facts: list[tuple[str, str]]) -> None:
        from bot.user_facts import MAX_FACTS_PER_USER, is_single

        if not user_id or not facts:
            return
        now = int(time.time())
        async with session_factory() as session:
            for kind, value in facts:
                if is_single(kind):
                    await session.execute(delete(UserFact).where(
                        UserFact.user_id == user_id, UserFact.kind == kind, UserFact.value != value))
                exists = await session.scalar(select(UserFact).where(
                    UserFact.user_id == user_id, UserFact.kind == kind, UserFact.value == value))
                if exists is not None:
                    exists.updated_at = now
                else:
                    session.add(UserFact(user_id=user_id, kind=kind[:16], value=value[:120], updated_at=now))
            await session.commit()
            old = list((await session.scalars(
                select(UserFact.id).where(UserFact.user_id == user_id)
                .order_by(UserFact.updated_at.desc(), UserFact.id.desc()).offset(MAX_FACTS_PER_USER)
            )).all())
            if old:
                await session.execute(delete(UserFact).where(UserFact.id.in_(old)))
                await session.commit()

    @staticmethod
    async def list(user_id: int) -> list[tuple[str, str]]:
        async with session_factory() as session:
            rows = (await session.scalars(
                select(UserFact).where(UserFact.user_id == user_id).order_by(UserFact.id)
            )).all()
            return [(r.kind, r.value) for r in rows]

    @staticmethod
    async def forget_kind(user_id: int, kind: str) -> None:
        async with session_factory() as session:
            await session.execute(delete(UserFact).where(UserFact.user_id == user_id, UserFact.kind == kind))
            await session.commit()

    @staticmethod
    async def forget(user_id: int) -> None:
        async with session_factory() as session:
            await session.execute(delete(UserFact).where(UserFact.user_id == user_id))
            await session.commit()


class MatureManager:
    @staticmethod
    async def get_profile(user_id: int) -> MatureProfile:
        async with session_factory() as session:
            row = await session.get(MatureProfile, user_id)
            if row is None:
                row = MatureProfile(user_id=user_id, updated_at=int(time.time()))
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def update_profile(user_id: int, **values) -> MatureProfile:
        allowed = {"intensity", "style", "safeword", "limits", "voice_replies"}
        clean = {k: v for k, v in values.items() if k in allowed}
        clean["updated_at"] = int(time.time())
        async with session_factory() as session:
            row = await session.get(MatureProfile, user_id)
            if row is None:
                row = MatureProfile(user_id=user_id, **clean)
                session.add(row)
            else:
                for key, value in clean.items():
                    setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def get_session(user_id: int, chat_id: int) -> MatureSession:
        async with session_factory() as session:
            result = await session.execute(
                select(MatureSession).where(
                    MatureSession.user_id == user_id,
                    MatureSession.chat_id == chat_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = MatureSession(user_id=user_id, chat_id=chat_id)
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def start_session(user_id: int, chat_id: int, title: str) -> MatureSession:
        now = int(time.time())
        async with session_factory() as session:
            result = await session.execute(
                select(MatureSession).where(
                    MatureSession.user_id == user_id,
                    MatureSession.chat_id == chat_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = MatureSession(user_id=user_id, chat_id=chat_id)
                session.add(row)
            row.active = True
            row.paused = False
            row.title = title[:1200]
            row.summary = ""
            row.turn_count = 0
            row.chemistry = 0
            row.started_at = now
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def set_session_state(user_id: int, chat_id: int, *, active: bool | None = None, paused: bool | None = None) -> MatureSession:
        row = await MatureManager.get_session(user_id, chat_id)
        async with session_factory() as session:
            current = await session.get(MatureSession, row.id)
            if active is not None:
                current.active = active
            if paused is not None:
                current.paused = paused
            current.updated_at = int(time.time())
            await session.commit()
            await session.refresh(current)
            return current

    @staticmethod
    async def record_turn(user_id: int, chat_id: int, user_text: str, answer: str) -> MatureSession:
        row = await MatureManager.get_session(user_id, chat_id)
        async with session_factory() as session:
            current = await session.get(MatureSession, row.id)
            current.turn_count = int(current.turn_count or 0) + 1
            # Chemistry is a playful session meter, not a consent signal.
            current.chemistry = min(100, int(current.chemistry or 0) + 2 + (1 if len(user_text) > 80 else 0))
            compact = f"U: {user_text.strip()}\nK: {answer.strip()}"[-2400:]
            current.summary = ((current.summary or "") + "\n" + compact)[-6000:]
            current.updated_at = int(time.time())
            await session.commit()
            await session.refresh(current)
            return current


class ChatSpeechManager:
    """Persisted per-chat speech freedom without coupling ai_client to kira_next."""

    VALID = {"clean", "natural", "free"}

    @staticmethod
    async def get(chat_id: int) -> str:
        async with session_factory() as session:
            row = await session.get(ChatMemorySettings, chat_id)
            if row is None:
                row = ChatMemorySettings(chat_id=chat_id, updated_at=int(time.time()))
                session.add(row)
                await session.commit()
                await session.refresh(row)
            value = (getattr(row, "speech_style", None) or "free").strip().lower()
            return value if value in ChatSpeechManager.VALID else "free"

    @staticmethod
    async def set(chat_id: int, value: str) -> str:
        value = (value or "natural").strip().lower()
        if value not in ChatSpeechManager.VALID:
            raise ValueError("unknown speech style")
        async with session_factory() as session:
            row = await session.get(ChatMemorySettings, chat_id)
            if row is None:
                row = ChatMemorySettings(chat_id=chat_id, updated_at=int(time.time()))
                session.add(row)
            row.speech_style = value
            row.updated_at = int(time.time())
            await session.commit()
            return value


class ChatSettingsManager:
    @staticmethod
    async def get(chat_id: int) -> ChatSettings:
        async with session_factory() as session:
            row = await session.get(ChatSettings, chat_id)
            if row is None:
                row = ChatSettings(chat_id=chat_id)
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    @staticmethod
    async def update(chat_id: int, **values) -> ChatSettings:
        allowed = {"anti_spam", "flood_limit", "flood_window", "links_allowed", "ai_enabled", "mature_mode", "auto_voice", "auto_voice_chance", "last_auto_voice_at"}
        safe_values = {k: v for k, v in values.items() if k in allowed}
        async with session_factory() as session:
            row = await session.get(ChatSettings, chat_id)
            if row is None:
                row = ChatSettings(chat_id=chat_id)
                session.add(row)
            for key, value in safe_values.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def auto_voice_chats() -> list[ChatSettings]:
        async with session_factory() as session:
            result = await session.execute(
                select(ChatSettings).where(ChatSettings.auto_voice.is_(True))
            )
            return list(result.scalars().all())


class BlacklistManager:
    @staticmethod
    async def is_blocked(user_id: int, chat_id: int = 0) -> bool:
        async with session_factory() as session:
            row = await session.scalar(select(Blacklist.id).where(
                Blacklist.user_id == user_id,
                or_(Blacklist.chat_id == 0, Blacklist.chat_id == chat_id),
            ).limit(1))
            return row is not None

    @staticmethod
    async def add(user_id: int, chat_id: int, reason: str, now: int) -> None:
        async with session_factory() as session:
            row = await session.scalar(select(Blacklist).where(
                Blacklist.user_id == user_id,
                Blacklist.chat_id == chat_id,
            ))
            if row:
                row.reason = reason
                row.created_at = now
            else:
                session.add(Blacklist(user_id=user_id, chat_id=chat_id, reason=reason, created_at=now))
            await session.commit()

    @staticmethod
    async def remove(user_id: int, chat_id: int) -> bool:
        async with session_factory() as session:
            result = await session.execute(delete(Blacklist).where(
                Blacklist.user_id == user_id,
                Blacklist.chat_id == chat_id,
            ))
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def list(chat_id: int | None = None) -> list[Blacklist]:
        async with session_factory() as session:
            stmt = select(Blacklist).order_by(Blacklist.id.desc())
            if chat_id is not None:
                stmt = stmt.where(Blacklist.chat_id == chat_id)
            rows = await session.scalars(stmt)
            return list(rows.all())


class AuditLogManager:
    @staticmethod
    async def add(chat_id: int, actor_id: int, action: str, details: str = "", target_id: int | None = None, now: int = 0) -> None:
        async with session_factory() as session:
            session.add(AuditLog(
                chat_id=chat_id,
                actor_id=actor_id,
                target_id=target_id,
                action=action[:64],
                details=details[:4000],
                created_at=now,
            ))
            await session.commit()

    @staticmethod
    async def recent(limit: int = 100) -> list[AuditLog]:
        async with session_factory() as session:
            rows = await session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
            return list(rows.all())


class StatsManager:
    @staticmethod
    async def counts() -> dict[str, int]:
        async with session_factory() as session:
            async def count(model):
                return int((await session.scalar(select(func.count()).select_from(model))) or 0)
            return {
                "users": await count(User),
                "chats": await count(Chat),
                "characters": await count(Character),
                "rps": await count(RPTrigger),
                "mems": await count(Mem),
                "reminders": await count(Reminder),
                "inventory": await count(InventoryItem),
                "blacklist": await count(Blacklist),
            }


async def cleanup_old_data(now: int | None = None) -> dict[str, int]:
    """Prune rows that are operational history rather than permanent user data."""
    now = int(now or time.time())
    audit_cutoff = now - 90 * 24 * 60 * 60
    reminder_cutoff = now - 30 * 24 * 60 * 60
    async with session_factory() as session:
        audit_result = await session.execute(
            delete(AuditLog).where(AuditLog.created_at > 0, AuditLog.created_at < audit_cutoff)
        )
        reminder_result = await session.execute(
            delete(Reminder).where(
                Reminder.enabled.is_(False),
                Reminder.created_at > 0,
                Reminder.created_at < reminder_cutoff,
            )
        )
        await session.commit()
        return {
            "audit": int(audit_result.rowcount or 0),
            "reminders": int(reminder_result.rowcount or 0),
        }


async def database_maintenance() -> None:
    """Lightweight online SQLite maintenance; safe while the bot is running."""
    async with engine.connect() as conn:
        if conn.dialect.name == "sqlite":
            await conn.execute(text("PRAGMA optimize"))
            await conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))


async def add_default():
    async with session_factory() as session:
        for race_name in DEFAULT_RACES:
            exists = await session.scalar(
                select(select(Race).where(Race.name == race_name).exists())
            )
            if not exists:
                session.add(Race(name=race_name))

        for class_name in DEFAULT_CLASSES:
            exists = await session.scalar(
                select(select(Class).where(Class.name == class_name).exists())
            )
            if not exists:
                session.add(Class(name=class_name))

        await session.commit()


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(TableBase.metadata.create_all)
        await conn.run_sync(_sync_missing_columns)


def _sync_missing_columns(connection: Connection) -> None:
    """
    Лёгкая авто-миграция для SQLite:
    добавляет отсутствующие столбцы в уже существующие таблицы.
    """
    if connection.dialect.name != "sqlite":
        return

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    for table in TableBase.metadata.sorted_tables:
        if table.name not in tables:
            continue

        existing_columns = {
            column["name"] for column in inspector.get_columns(table.name)
        }

        for column in table.columns:
            if column.name in existing_columns:
                continue

            if column.primary_key or column.unique:
                log.warning(
                    "Пропуск авто-миграции для %s.%s: требуется ручная миграция (primary key/unique).",
                    table.name,
                    column.name,
                )
                continue

            statement = _build_add_column_statement(table.name, column, connection)
            connection.execute(text(statement))
            log.warning("Добавлен столбец %s.%s", table.name, column.name)


def _build_add_column_statement(table_name: str, column, connection: Connection) -> str:
    quoted_table = _quote_name(table_name)
    quoted_column = _quote_name(column.name)
    column_type = column.type.compile(dialect=connection.dialect)

    statement = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {column_type}"
    default_sql = _column_default_sql(column)

    if default_sql is not None:
        statement += f" DEFAULT {default_sql}"

    if not column.nullable and default_sql is not None:
        statement += " NOT NULL"
    elif not column.nullable:
        log.warning(
            "Столбец %s.%s добавлен nullable: для NOT NULL нужен server_default или ручная миграция.",
            table_name,
            column.name,
        )

    foreign_keys = list(column.foreign_keys)
    if len(foreign_keys) == 1:
        fk = foreign_keys[0]
        fk_table, fk_column = _split_target(fk.target_fullname)
        statement += f" REFERENCES {_quote_name(fk_table)}({_quote_name(fk_column)})"

    return statement


def _split_target(target_fullname: str) -> tuple[str, str]:
    parts = target_fullname.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return target_fullname, "id"


def _column_default_sql(column) -> Optional[str]:
    if column.server_default is not None:
        arg = getattr(column.server_default, "arg", None)
        if arg is not None:
            return str(arg)

    if column.default is not None and getattr(column.default, "is_scalar", False):
        return _to_sql_literal(column.default.arg)

    return None


def _to_sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _quote_name(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
