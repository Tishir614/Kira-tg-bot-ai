from typing import Literal, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class TableBase(DeclarativeBase):
    pass


class Chat(TableBase):
    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    admin_chat_id: Mapped[Optional[int]]
    created_at: Mapped[int] = mapped_column(Integer, default=0)

    mems: Mapped[list["Mem"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )


class Character(TableBase):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    description: Mapped[str]

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    user: Mapped["User"] = relationship(back_populates="character")

    married_id: Mapped[Optional[int]] = mapped_column(ForeignKey("characters.id"), nullable=True)
    married: Mapped[Optional["Character"]] = relationship(
        remote_side="Character.id",
        uselist=False,
    )


class Warn(TableBase):
    __tablename__ = "warns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    chat_id: Mapped[int]
    cause: Mapped[str]
    created_at: Mapped[int]
    time: Mapped[float]
    user: Mapped["User"] = relationship(back_populates="warns")


class User(TableBase):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    sudo: Mapped[bool] = mapped_column(default=False)
    warns: Mapped[list[Warn]] = relationship(back_populates="user")
    character: Mapped[Optional["Character"]] = relationship(
        "Character",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    penis_len: Mapped[float] = mapped_column(default=0)
    masturbate_cooldown_until: Mapped[int] = mapped_column(default=0)
    tail_fluff: Mapped[float] = mapped_column(default=0)
    tail_cooldown_until: Mapped[int] = mapped_column(default=0)
    alcohol_score: Mapped[float] = mapped_column(default=0)
    alcohol_cooldown_until: Mapped[int] = mapped_column(default=0)
    active_effect: Mapped[str] = mapped_column(String(64), default="")
    active_effect_until: Mapped[int] = mapped_column(Integer, default=0)

    # Экономика/профиль. Значения по умолчанию позволяют безопасно добавить
    # столбцы в существующую SQLite через лёгкую авто-миграцию проекта.
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    coins: Mapped[int] = mapped_column(Integer, default=100)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_daily_at: Mapped[int] = mapped_column(Integer, default=0)
    last_work_at: Mapped[int] = mapped_column(Integer, default=0)
    bio: Mapped[str] = mapped_column(String(180), default="")
    # Kira 1.2 profile customization. Telegram itself does not support arbitrary
    # text colors, so profile_color is rendered in Mini App and represented by
    # a color badge in regular bot messages.
    gender: Mapped[str] = mapped_column(String(24), default="unspecified")
    profile_color: Mapped[str] = mapped_column(String(7), default="#E8BDFF")
    profile_title: Mapped[str] = mapped_column(String(48), default="")
    profile_badge: Mapped[str] = mapped_column(String(16), default="🦊")
    profile_theme: Mapped[str] = mapped_column(String(24), default="violet")
    birthday_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birthday_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    adult_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class UserNickname(TableBase):
    """User-selected nickname, scoped to a Telegram chat (or chat_id=0 as global fallback)."""
    __tablename__ = "user_nicknames"
    __table_args__ = (UniqueConstraint("user_id", "chat_id", name="uq_user_nickname_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    chat_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    nickname: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class Race(TableBase):
    __tablename__ = "races"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]


class Class(TableBase):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]


class RPTrigger(TableBase):
    __tablename__ = "rps"
    __table_args__ = (
        UniqueConstraint("chat_id", "trigger", name="uq_rp_chat_trigger"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trigger: Mapped[str]
    answer: Mapped[str]
    type: Mapped[Literal["action", "emotion"]]
    chat_id: Mapped[int] = mapped_column(default=0)


class AniListMalCache(TableBase):
    __tablename__ = "anilist_mal_cache"

    anilist_id: Mapped[int] = mapped_column(primary_key=True)
    mal_id: Mapped[int]


class Mem(TableBase):
    __tablename__ = "mems"
    __table_args__ = (
        UniqueConstraint("chat_id", "sticker_id", name="uq_chat_sticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.chat_id", ondelete="CASCADE"))
    sticker_id: Mapped[str] = mapped_column(String(255))

    chat: Mapped["Chat"] = relationship(back_populates="mems")


class Reminder(TableBase):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    due_at: Mapped[int] = mapped_column(index=True)
    repeat_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int]
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryItem(TableBase):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("user_id", "item_key", name="uq_inventory_user_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    acquired_at: Mapped[int]


class Relationship(TableBase):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("user_id", "target_user_id", name="uq_relationship_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    target_user_id: Mapped[int] = mapped_column(index=True)
    friendship: Mapped[int] = mapped_column(Integer, default=0)
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    interactions: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int]


class AssistantMemory(TableBase):
    __tablename__ = "assistant_memory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int]


class UserFact(TableBase):
    __tablename__ = "user_facts"
    __table_args__ = (UniqueConstraint("user_id", "kind", "value", name="uq_user_fact"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[int]


class ChatSettings(TableBase):
    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    anti_spam: Mapped[bool] = mapped_column(Boolean, default=False)
    flood_limit: Mapped[int] = mapped_column(Integer, default=7)
    flood_window: Mapped[int] = mapped_column(Integer, default=8)
    links_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mature_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_voice_chance: Mapped[int] = mapped_column(Integer, default=20)
    last_auto_voice_at: Mapped[int] = mapped_column(Integer, default=0)


class DndCharacter(TableBase):
    """Extensible Mini App character sheet; JSON keeps old DB migrations safe."""
    __tablename__ = "dnd_characters"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120), default="Безымянный герой")
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class DndCampaign(TableBase):
    __tablename__ = "dnd_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    dm_user_id: Mapped[int] = mapped_column(index=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[int] = mapped_column(Integer, default=0)


class DndCampaignMember(TableBase):
    __tablename__ = "dnd_campaign_members"
    __table_args__ = (UniqueConstraint("campaign_id", "user_id", name="uq_dnd_campaign_member"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("dnd_campaigns.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(16), default="player")
    character_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    joined_at: Mapped[int] = mapped_column(Integer, default=0)


class DndRoll(TableBase):
    __tablename__ = "dnd_rolls"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    expression: Mapped[str] = mapped_column(String(32))
    result: Mapped[int]
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[int] = mapped_column(Integer, default=0)


class MatureProfile(TableBase):
    __tablename__ = "mature_profiles"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    intensity: Mapped[int] = mapped_column(Integer, default=3)
    style: Mapped[str] = mapped_column(String(32), default="balanced")
    safeword: Mapped[str] = mapped_column(String(64), default="стоп")
    limits: Mapped[str] = mapped_column(Text, default="")
    voice_replies: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class MatureSession(TableBase):
    __tablename__ = "mature_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "chat_id", name="uq_mature_session_user_chat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    chemistry: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class RPScene(TableBase):
    __tablename__ = "rp_scenes"
    __table_args__ = (UniqueConstraint("user_id", "chat_id", name="uq_rp_scene_user_chat"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(Text, default="")
    bot_char: Mapped[str] = mapped_column(Text, default="")
    user_char: Mapped[str] = mapped_column(Text, default="")
    setting: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    turns_json: Mapped[str] = mapped_column(Text, default="[]")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class RPCharacter(TableBase):
    __tablename__ = "rp_characters"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_rp_character_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(40))
    card: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class ConversationSummary(TableBase):
    __tablename__ = "conversation_summaries"
    __table_args__ = (UniqueConstraint("user_id", "chat_id", name="uq_conv_summary_user_chat"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int] = mapped_column(index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class Blacklist(TableBase):
    __tablename__ = "blacklist"
    __table_args__ = (
        UniqueConstraint("user_id", "chat_id", name="uq_blacklist_user_chat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    chat_id: Mapped[int] = mapped_column(default=0, index=True)  # 0 = global
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int]


class AuditLog(TableBase):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(index=True)
    actor_id: Mapped[int] = mapped_column(index=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int]
class GroupActivity(TableBase):
    """Per-chat activity counters used for local leaderboards and levels."""
    __tablename__ = "group_activity"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_group_activity_chat_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    display_name: Mapped[str] = mapped_column(String(180), default="Пользователь")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    text_messages: Mapped[int] = mapped_column(Integer, default=0)
    media_messages: Mapped[int] = mapped_column(Integer, default=0)
    voice_messages: Mapped[int] = mapped_column(Integer, default=0)
    activity_xp: Mapped[int] = mapped_column(Integer, default=0)
    activity_level: Mapped[int] = mapped_column(Integer, default=1)
    last_message_at: Mapped[int] = mapped_column(Integer, default=0)


class GroupConversationSettings(TableBase):
    """Natural group conversation controls kept separate from legacy chat settings."""
    __tablename__ = "group_conversation_settings"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    spontaneous_chance: Mapped[int] = mapped_column(Integer, default=4)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=900)
    last_spoke_at: Mapped[int] = mapped_column(Integer, default=0)


class GroupRulesSettings(TableBase):
    """Per-chat automatic rules moderation settings."""
    __tablename__ = "group_rules_settings"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)




class GroupStaff(TableBase):
    """Custom per-chat staff roles managed by Kira."""
    __tablename__ = "group_staff"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_group_staff_chat_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(16), default="helper")
    assigned_by: Mapped[int] = mapped_column(Integer, default=0)
    assigned_at: Mapped[int] = mapped_column(Integer, default=0)


class CommunityMarriage(TableBase):
    """Lightweight marriage system scoped to one Telegram group."""
    __tablename__ = "community_marriages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    user_a_id: Mapped[int] = mapped_column(Integer, index=True)
    user_b_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=0)


class MarriageProposal(TableBase):
    __tablename__ = "marriage_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    proposer_id: Mapped[int] = mapped_column(Integer, index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=0)


class MatureRPProposal(TableBase):
    """Consent-gated adult RP action request."""
    __tablename__ = "mature_rp_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    initiator_id: Mapped[int] = mapped_column(Integer, index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    action_code: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=0)


class RecoveryIncident(TableBase):
    """Small persistent journal of automatic recovery actions."""
    __tablename__ = "recovery_incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=0)

class GroupReport(TableBase):
    """User complaint/report submitted inside a group."""
    __tablename__ = "group_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    reporter_id: Mapped[int] = mapped_column(Integer, index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    target_name: Mapped[str] = mapped_column(String(180), default="Пользователь")
    message_id: Mapped[int] = mapped_column(Integer, default=0)
    message_text: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="Без причины")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    handled_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    handled_at: Mapped[int] = mapped_column(Integer, default=0)
    resolution: Mapped[str] = mapped_column(Text, default="")


class MemoryPrivacy(TableBase):
    __tablename__ = "memory_privacy"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personal_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_group_history: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_profile_learning: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class LongTermMemory(TableBase):
    __tablename__ = "long_term_memory"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    chat_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="fact", index=True)
    key: Mapped[str] = mapped_column(String(96), default="")
    value: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class ChatMemorySettings(TableBase):
    __tablename__ = "chat_memory_settings"
    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    personality: Mapped[str] = mapped_column(String(24), default="friendly")
    speech_style: Mapped[str] = mapped_column(String(16), default="free")
    moderator_mode: Mapped[str] = mapped_column(String(16), default="assist")
    moderator_strictness: Mapped[int] = mapped_column(Integer, default=3)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class ChatMemoryMessage(TableBase):
    __tablename__ = "chat_memory_messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_chat_memory_message"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    display_name: Mapped[str] = mapped_column(String(180), default="Пользователь")
    text: Mapped[str] = mapped_column(Text, default="")
    semantic_hash: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=0, index=True)


class MemoryEvent(TableBase):
    __tablename__ = "memory_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="event", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    source_message_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer, default=0, index=True)


class AIModerationIncident(TableBase):
    __tablename__ = "ai_moderation_incidents"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(32), default="other")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(32), default="flag")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=0, index=True)


class PendingAdminAction(TableBase):
    __tablename__ = "pending_admin_actions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True)
    action_json: Mapped[str] = mapped_column(Text, default="{}")
    human_summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
