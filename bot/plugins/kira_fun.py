from __future__ import annotations

import hashlib
import html
import random
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.sql import NicknameManager

router = Router(name="kira-fun")


TRUTH_QUESTIONS = (
    "Какой маленький поступок другого человека ты помнишь до сих пор?",
    "Какую привычку ты бы с удовольствием выключил(а) на неделю?",
    "Какой у тебя самый странный, но безобидный страх?",
    "Какой комплимент тебе запомнился сильнее всего?",
    "Если бы можно было мгновенно освоить один навык, что бы ты выбрал(а)?",
    "Какую песню ты можешь переслушивать слишком много раз?",
    "Какой мем лучше всего описывает тебя сегодня?",
    "Какой вымышленный мир ты бы посетил(а) на один день?",
    "Что тебе обычно помогает вернуть настроение?",
    "Какую смешную ошибку ты недавно допустил(а)?",
)

DARES = (
    "Отправь в чат три эмодзи, которые описывают твой сегодняшний день.",
    "Придумай себе нелепый титул и используй его в следующем сообщении.",
    "Сделай искренний комплимент любому участнику чата.",
    "Напиши одно предложение так, будто его произносит злодей из мультфильма.",
    "Опиши своё настроение названием несуществующего фильма.",
    "Выбери случайный предмет рядом и придумай ему легендарную предысторию.",
    "Напиши мини-историю ровно из пяти слов.",
    "Отправь гифку или стикер, который максимально не подходит к текущей теме.",
    "Придумай новое смешное название этому чату.",
    "Следующее сообщение напиши от лица очень серьёзной лисы-детектива.",
)

ORACLE_LINES = (
    "Сегодня удача прячется в сообщении, которое ты почти решил(а) не отправлять.",
    "Лисий хвост предсказывает: маленькая идея внезапно окажется полезнее большого плана.",
    "Сегодня лучше сначала закончить одну мелочь, а уже потом штурмовать дракона задач.",
    "К вечеру тебя может найти неожиданный повод улыбнуться. Не прогоняй его.",
    "День благоприятен для творчества, странных идей и одной хорошей шутки.",
    "Сегодняшний бафф: +10 к любопытству и +5 к терпению к людям.",
    "Неожиданный союзник дня: случайность. Но пароль от сервера ей всё равно не давай.",
    "Сегодня стоит написать тому, с кем давно хотел(а) нормально поговорить.",
    "Лисий оракул видит чай, музыку и внезапно продуктивные двадцать минут.",
    "Главный квест дня: не откладывать одну вещь, которая занимает меньше пяти минут.",
)

COMPLIMENTS = (
    "у тебя редкий талант делать разговор живее одним сообщением",
    "с тобой у чата появляется собственный характер",
    "ты умеешь приносить в разговор ту самую нужную искру",
    "у тебя очень узнаваемая энергия, её сложно спутать",
    "ты явно умеешь находить интересное там, где другие проходят мимо",
    "твоя суперспособность сегодня: делать атмосферу немного теплее",
    "у тебя хороший навык не быть фоновым персонажем собственной истории",
    "ты добавляешь чату больше красок, чем кажется на первый взгляд",
)

DUEL_MOVES = (
    ("⚡ молниеносный финт", "🛡 непробиваемую защиту"),
    ("🦊 лисий манёвр", "🌪 вихревой ответ"),
    ("🎭 отвлекающую драму", "🧠 тактический расчёт"),
    ("🍳 легендарную сковородку", "🥖 боевой багет"),
    ("🌙 лунный рывок", "☀️ солнечный контрудар"),
)


def _arg(message: Message) -> str:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def _name(user, chat_id: int) -> str:
    nick = await NicknameManager.get(user.id, chat_id)
    return nick or user.full_name or user.username or str(user.id)


@router.message(Command("nick"))
async def nick_cmd(message: Message):
    if not message.from_user:
        return
    raw = _arg(message)
    if not raw:
        current, global_name = await NicknameManager.get_scoped(message.from_user.id, message.chat.id)
        effective = current or global_name
        await message.reply(
            "🪪 <b>Ник Киры</b>\n"
            f"В этом чате: <b>{html.escape(current) if current else 'не задан'}</b>\n"
            f"Глобальный: <b>{html.escape(global_name) if global_name else 'не задан'}</b>\n"
            f"Сейчас Кира использует: <b>{html.escape(effective) if effective else html.escape(message.from_user.full_name)}</b>\n\n"
            "Установить здесь: <code>/ник Лис</code>\n"
            "Для всех чатов: <code>/ник глобально Лис</code>"
        )
        return
    scope = message.chat.id
    lowered = raw.casefold()
    if lowered.startswith("глобально ") or lowered.startswith("global "):
        raw = raw.split(maxsplit=1)[1]
        scope = 0
    try:
        nickname = await NicknameManager.set(message.from_user.id, scope, raw)
    except ValueError as exc:
        await message.reply("🪪 " + html.escape(str(exc)))
        return
    where = "во всех чатах, где нет отдельного ника" if scope == 0 else "в этом чате"
    await message.reply(
        f"🦊 Запомнила: <b>{html.escape(nickname)}</b>. Буду использовать этот ник {where}, в том числе в RP."
    )


@router.message(Command("my_nick"))
@router.message(F.text.casefold() == "мой ник")
async def my_nick_cmd(message: Message):
    if not message.from_user:
        return
    current, global_name = await NicknameManager.get_scoped(message.from_user.id, message.chat.id)
    effective = current or global_name
    if not effective:
        await message.reply("🪪 Ник пока не задан. Напиши <code>/ник Лис</code>.")
        return
    await message.reply(
        f"🪪 Кира зовёт тебя <b>{html.escape(effective)}</b>."
        + (f"\nГлобальный запасной ник: <b>{html.escape(global_name)}</b>." if current and global_name else "")
    )


@router.message(Command("remove_nick"))
async def remove_nick_cmd(message: Message):
    if not message.from_user:
        return
    raw = _arg(message).casefold()
    scope = 0 if raw in {"global", "глобально", "везде"} else message.chat.id
    deleted = await NicknameManager.delete(message.from_user.id, scope)
    if deleted:
        await message.reply("🧹 Ник удалён." + (" Глобальный." if scope == 0 else " Для этого чата."))
    else:
        await message.reply("🪪 Здесь такого сохранённого ника нет.")


@router.message(Command("truth"))
async def truth_cmd(message: Message):
    name = await _name(message.from_user, message.chat.id) if message.from_user else "Игрок"
    await message.reply(f"🎭 <b>Правда для {html.escape(name)}</b>\n{random.choice(TRUTH_QUESTIONS)}")


@router.message(Command("dare"))
async def dare_cmd(message: Message):
    name = await _name(message.from_user, message.chat.id) if message.from_user else "Игрок"
    await message.reply(f"🎯 <b>Действие для {html.escape(name)}</b>\n{random.choice(DARES)}")


@router.message(Command("oracle"))
async def oracle_cmd(message: Message):
    if not message.from_user:
        return
    name = await _name(message.from_user, message.chat.id)
    seed = f"{date.today().isoformat()}:{message.chat.id}:{message.from_user.id}:kira-oracle".encode()
    idx = int.from_bytes(hashlib.blake2b(seed, digest_size=4).digest(), "big") % len(ORACLE_LINES)
    await message.reply(
        f"🔮 <b>Лисий оракул для {html.escape(name)}</b>\n{ORACLE_LINES[idx]}\n\n"
        "<i>Это игровое предсказание и оно не меняется до завтра.</i>"
    )


@router.message(Command("duel"))
async def duel_cmd(message: Message):
    if not message.from_user:
        return
    reply = message.reply_to_message
    if not reply or not reply.from_user or reply.from_user.is_bot or reply.from_user.id == message.from_user.id:
        await message.reply("⚔️ Ответь <code>/дуэль</code> на сообщение другого участника.")
        return
    left = await _name(message.from_user, message.chat.id)
    right = await _name(reply.from_user, message.chat.id)
    winner, loser = ((left, right) if random.getrandbits(1) else (right, left))
    move_a, move_b = random.choice(DUEL_MOVES)
    await message.reply(
        f"⚔️ <b>{html.escape(left)}</b> использует {move_a}, а <b>{html.escape(right)}</b> отвечает через {move_b}.\n"
        f"🏆 Побеждает <b>{html.escape(winner)}</b>! <i>{html.escape(loser)} требует реванш где-то в параллельной вселенной.</i>"
    )


@router.message(Command("compliment"))
async def compliment_cmd(message: Message):
    if not message.from_user:
        return
    target = message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot else message.from_user
    name = await _name(target, message.chat.id)
    await message.reply(f"✨ <b>{html.escape(name)}</b>, {random.choice(COMPLIMENTS)}.")
