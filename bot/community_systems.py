from __future__ import annotations

import time
from aiogram.enums import ChatMemberStatus
from sqlalchemy import delete, or_, select

from bot.owners import is_owner
from bot.sql import session_factory
from bot.sql.orm_tables import CommunityMarriage, GroupStaff, MarriageProposal, MatureRPProposal


ROLE_RANK = {"member": 0, "helper": 1, "moderator": 2, "admin": 3, "owner": 4}
ROLE_LABELS = {
    "member": "Участник",
    "helper": "Помощник",
    "moderator": "Модератор",
    "admin": "Администратор",
    "owner": "Владелец",
}

ROLE_PERMISSIONS = {
    "member": set(),
    "helper": {"warn", "reports_view"},
    "moderator": {
        "warn",
        "unwarn",
        "mute",
        "kick",
        "reports_view",
        "reports_manage",
        "modlog",
    },
    "admin": {
        "warn",
        "unwarn",
        "mute",
        "kick",
        "ban",
        "reports_view",
        "reports_manage",
        "modlog",
        "settings",
        "staff_manage",
    },
    "owner": {"*"},
}


class GroupStaffManager:
    @staticmethod
    async def get(chat_id: int, user_id: int) -> GroupStaff | None:
        async with session_factory() as session:
            return await session.scalar(
                select(GroupStaff).where(GroupStaff.chat_id == chat_id, GroupStaff.user_id == user_id)
            )

    @staticmethod
    async def set(chat_id: int, user_id: int, role: str, assigned_by: int, now: int | None = None) -> GroupStaff:
        role = role.casefold().strip()
        if role not in {"helper", "moderator", "admin"}:
            raise ValueError("Неизвестная роль")
        async with session_factory() as session:
            row = await session.scalar(
                select(GroupStaff).where(GroupStaff.chat_id == chat_id, GroupStaff.user_id == user_id)
            )
            if row is None:
                row = GroupStaff(chat_id=chat_id, user_id=user_id)
                session.add(row)
            row.role = role
            row.assigned_by = assigned_by
            row.assigned_at = int(now or time.time())
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def remove(chat_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            result = await session.execute(
                delete(GroupStaff).where(GroupStaff.chat_id == chat_id, GroupStaff.user_id == user_id)
            )
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def list(chat_id: int) -> list[GroupStaff]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(GroupStaff).where(GroupStaff.chat_id == chat_id).order_by(GroupStaff.role.desc(), GroupStaff.id.asc())
            )
            return list(rows.all())


async def resolve_group_role(bot, chat_id: int, user_id: int, *, owner_id: int = 0) -> str:
    if is_owner(user_id) or (owner_id and user_id == owner_id):
        return "owner"
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.CREATOR:
            return "owner"
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            return "admin"
    except Exception:
        pass
    row = await GroupStaffManager.get(chat_id, user_id)
    return row.role if row and row.role in ROLE_RANK else "member"


def role_has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


class CommunityMarriageManager:
    PROPOSAL_TTL = 24 * 60 * 60

    @staticmethod
    async def get(chat_id: int, user_id: int) -> CommunityMarriage | None:
        async with session_factory() as session:
            return await session.scalar(
                select(CommunityMarriage).where(
                    CommunityMarriage.chat_id == chat_id,
                    or_(CommunityMarriage.user_a_id == user_id, CommunityMarriage.user_b_id == user_id),
                )
            )

    @staticmethod
    async def partner_id(chat_id: int, user_id: int) -> int | None:
        row = await CommunityMarriageManager.get(chat_id, user_id)
        if not row:
            return None
        return row.user_b_id if row.user_a_id == user_id else row.user_a_id

    @staticmethod
    async def propose(chat_id: int, proposer_id: int, target_id: int, now: int | None = None) -> MarriageProposal:
        if proposer_id == target_id:
            raise ValueError("Нельзя заключить брак с самим собой")
        if await CommunityMarriageManager.get(chat_id, proposer_id):
            raise ValueError("Ты уже состоишь в браке в этой беседе")
        if await CommunityMarriageManager.get(chat_id, target_id):
            raise ValueError("Этот пользователь уже состоит в браке в этой беседе")
        now = int(now or time.time())
        async with session_factory() as session:
            # Старые незавершённые предложения этого пользователя не должны копиться.
            await session.execute(
                delete(MarriageProposal).where(
                    MarriageProposal.chat_id == chat_id,
                    MarriageProposal.proposer_id == proposer_id,
                    MarriageProposal.status == "pending",
                )
            )
            row = MarriageProposal(
                chat_id=chat_id,
                proposer_id=proposer_id,
                target_id=target_id,
                status="pending",
                created_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def get_proposal(proposal_id: int) -> MarriageProposal | None:
        async with session_factory() as session:
            return await session.get(MarriageProposal, proposal_id)

    @staticmethod
    async def accept(proposal_id: int, actor_id: int, now: int | None = None) -> CommunityMarriage:
        now = int(now or time.time())
        async with session_factory() as session:
            proposal = await session.get(MarriageProposal, proposal_id)
            if not proposal or proposal.status != "pending":
                raise ValueError("Предложение уже недействительно")
            if proposal.target_id != actor_id:
                raise PermissionError("Это предложение адресовано другому пользователю")
            if now - proposal.created_at > CommunityMarriageManager.PROPOSAL_TTL:
                proposal.status = "expired"
                await session.commit()
                raise ValueError("Срок предложения истёк")
            existing = await session.scalar(
                select(CommunityMarriage).where(
                    CommunityMarriage.chat_id == proposal.chat_id,
                    or_(
                        CommunityMarriage.user_a_id.in_([proposal.proposer_id, proposal.target_id]),
                        CommunityMarriage.user_b_id.in_([proposal.proposer_id, proposal.target_id]),
                    ),
                )
            )
            if existing:
                raise ValueError("Кто-то из участников уже состоит в браке")
            a, b = sorted((proposal.proposer_id, proposal.target_id))
            marriage = CommunityMarriage(
                chat_id=proposal.chat_id,
                user_a_id=a,
                user_b_id=b,
                created_at=now,
            )
            proposal.status = "accepted"
            session.add(marriage)
            await session.commit()
            await session.refresh(marriage)
            return marriage

    @staticmethod
    async def decline(proposal_id: int, actor_id: int) -> bool:
        async with session_factory() as session:
            proposal = await session.get(MarriageProposal, proposal_id)
            if not proposal or proposal.status != "pending":
                return False
            if proposal.target_id != actor_id:
                raise PermissionError("Это предложение адресовано другому пользователю")
            proposal.status = "declined"
            await session.commit()
            return True

    @staticmethod
    async def divorce(chat_id: int, user_id: int) -> int | None:
        async with session_factory() as session:
            row = await session.scalar(
                select(CommunityMarriage).where(
                    CommunityMarriage.chat_id == chat_id,
                    or_(CommunityMarriage.user_a_id == user_id, CommunityMarriage.user_b_id == user_id),
                )
            )
            if row is None:
                return None
            partner = row.user_b_id if row.user_a_id == user_id else row.user_a_id
            await session.delete(row)
            await session.commit()
            return partner

    @staticmethod
    async def list(chat_id: int, limit: int = 20) -> list[CommunityMarriage]:
        async with session_factory() as session:
            rows = await session.scalars(
                select(CommunityMarriage)
                .where(CommunityMarriage.chat_id == chat_id)
                .order_by(CommunityMarriage.id.desc())
                .limit(max(1, min(int(limit), 50)))
            )
            return list(rows.all())


MATURE_RP_ACTIONS = {
    "sex": {
        "triggers": {"секс", "переспать", "трахнуть"},
        "text": "💞 {u1} и {u2} уединились и занялись сексом по взаимному согласию.",
    },
    "intimate": {
        "triggers": {"интим", "отсосать"},
        "text": "🔞 {u1} и {u2} согласились на интимное RP-действие и уединились.",
    },
    "night": {
        "triggers": {"ночь вместе", "провести ночь"},
        "text": "🌙 {u1} и {u2} решили провести ночь вместе.",
    },
    "passionate_kiss": {
        "triggers": {"страстно поцеловать", "горячий поцелуй"},
        "text": "💋 {u1} страстно поцеловал(а) {u2}.",
    },
    "bed_cuddle": {
        "triggers": {"в кровать", "обниматься в кровати"},
        "text": "🛏️ {u1} и {u2} устроились рядом и обнялись.",
    },
    "flirt": {
        "triggers": {"соблазнить", "флирт 18+"},
        "text": "😏 {u1} начал(а) откровенно флиртовать с {u2}.",
    },
}

MATURE_TRIGGER_TO_CODE = {
    trigger: code for code, data in MATURE_RP_ACTIONS.items() for trigger in data["triggers"]
}


class MatureRPProposalManager:
    TTL = 10 * 60

    @staticmethod
    async def create(chat_id: int, initiator_id: int, target_id: int, action_code: str, now: int | None = None) -> MatureRPProposal:
        if action_code not in MATURE_RP_ACTIONS:
            raise ValueError("Неизвестное действие")
        if initiator_id == target_id:
            raise ValueError("Выбери другого участника")
        row = MatureRPProposal(
            chat_id=chat_id,
            initiator_id=initiator_id,
            target_id=target_id,
            action_code=action_code,
            status="pending",
            created_at=int(now or time.time()),
        )
        async with session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def get(proposal_id: int) -> MatureRPProposal | None:
        async with session_factory() as session:
            return await session.get(MatureRPProposal, proposal_id)

    @staticmethod
    async def decide(proposal_id: int, actor_id: int, *, accept: bool, now: int | None = None) -> MatureRPProposal:
        now = int(now or time.time())
        async with session_factory() as session:
            row = await session.get(MatureRPProposal, proposal_id)
            if row is None or row.status != "pending":
                raise ValueError("Запрос уже недействителен")
            if row.target_id != actor_id:
                raise PermissionError("Этот запрос адресован другому пользователю")
            if now - row.created_at > MatureRPProposalManager.TTL:
                row.status = "expired"
                await session.commit()
                raise ValueError("Запрос истёк")
            row.status = "accepted" if accept else "declined"
            await session.commit()
            await session.refresh(row)
            return row
