from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from bot import log
from bot.ai_client import AIUnavailable, ai
from bot.rp_engine import RPStore, Scene, build_director_prompt, compose_user_prompt, parse_card, record_turn
from bot.runtime import metrics
from bot.sql import ChatSettingsManager, MatureManager, UserManager

router = Router(name="rp")

HELP = (
    "🎭 <b>Умный RP-модуль Киры</b>\n"
    "• <code>/rp start &lt;сцена&gt;</code> — начать сцену (дальше пиши обычными сообщениями)\n"
    "• <code>/rp char Имя | описание</code> — кого играет Кира\n"
    "• <code>/rp me Имя | описание</code> — твой персонаж\n"
    "• <code>/rp world &lt;мир/жанр&gt;</code> — сеттинг (фэнтези, киберпанк, школа магии…)\n"
    "• <code>/rp retry</code> — переписать последний ответ · <code>/rp undo</code> — откатить ход\n"
    "• <code>/rp recap</code> — краткое содержание · <code>/rp status</code>\n"
    "• <code>/rp pause</code> / <code>resume</code> / <code>stop</code>\n"
    "Вне роли пиши в двойных скобках: <code>(( ... ))</code>.\n"
    "Взрослый режим 18+ включается через <code>/mature accept</code> (один раз)."
)


def _arg(message: Message) -> str:
    parts = (message.text or "").strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def _adult(message: Message) -> bool:
    if not message.from_user:
        return False
    if not await UserManager.is_adult_confirmed(message.from_user.id):
        return False
    return bool((await ChatSettingsManager.get(message.chat.id)).mature_mode)


async def _send(message: Message, text: str) -> None:
    text = (text or "").strip() or "…"
    for i in range(0, len(text), 3900):
        await message.reply(text[i:i + 3900], parse_mode=None) if i == 0 else await message.answer(text[i:i + 3900], parse_mode=None)


async def _play(message: Message, scene: Scene, user_text: str, *, retry: bool = False) -> None:
    uid, cid = message.from_user.id, message.chat.id
    adult = await _adult(message)
    profile = await MatureManager.get_profile(uid)
    base = ai.MATURE_PROMPT if adult else ai.SYSTEM_PROMPT
    if retry:
        user_text_for_model = user_text + "\n\n(Перепиши ответ иначе: другие детали, другой поворот, тот же смысл хода.)"
    else:
        user_text_for_model = user_text
    try:
        metrics.ai_requests += 1
        async with ChatActionSender.typing(chat_id=cid, bot=message.bot):
            answer = await ai.respond(
                compose_user_prompt(scene, user_text_for_model),
                user_id=uid, chat_id=cid, remember=False,
                instructions=build_director_prompt(base, scene, adult=adult, safeword=profile.safeword if adult else ""),
                creative=True, max_tokens=900,
            )
        await record_turn(ai, uid, cid, scene, user_text, answer)
        await _send(message, answer)
    except AIUnavailable as exc:
        await message.reply(f"🦊 {html.escape(str(exc))}")
    except Exception:
        metrics.errors += 1
        log.exception("rp turn failed")
        await message.reply("🦊 Не смогла продолжить сцену: AI временно недоступен.")


@router.message(Command("rp"))
@router.message(F.text.regexp(r"(?i)^рп(?:\s|$)"))
async def rp_command(message: Message):
    if not message.from_user:
        return
    raw = _arg(message) if (message.text or "").startswith("/") else re.sub(r"(?i)^рп\s*", "", message.text or "").strip()
    uid, cid = message.from_user.id, message.chat.id
    cmd, _, rest = raw.partition(" ")
    cmd, rest = cmd.lower(), rest.strip()
    scene = await RPStore.get(uid, cid)

    if cmd in {"", "help", "помощь"}:
        await message.reply(HELP)
    elif cmd in {"start", "начать", "старт"}:
        if not rest:
            await message.reply("Опиши сцену: <code>/rp start ночной клуб, мы случайно встретились у бара</code>")
            return
        scene = await RPStore.start(uid, cid, rest)
        await message.reply(
            "🎭 <b>Сцена началась.</b> Пиши действия и реплики обычными сообщениями"
            + (" (в группе — ответом на сообщение Киры)." if message.chat.type != "private" else ".")
            + "\nВне роли: <code>(( ... ))</code>. Стоп: <code>/rp stop</code>."
        )
        await _play(message, scene, f"[Начало сцены] {rest}\nНачни сцену: опиши место и первый ход Киры.")
    elif cmd in {"char", "перс", "персонаж"}:
        await RPStore.update(uid, cid, bot_char=parse_card(rest))
        await message.reply("🦊 Персонаж Киры сохранён.")
    elif cmd in {"me", "я"}:
        await RPStore.update(uid, cid, user_char=parse_card(rest))
        await message.reply("🙂 Твой персонаж сохранён.")
    elif cmd in {"world", "мир", "сеттинг"}:
        await RPStore.update(uid, cid, setting=rest)
        await message.reply("🌍 Сеттинг сохранён.")
    elif cmd in {"pause", "пауза"}:
        await RPStore.update(uid, cid, paused=True)
        await message.reply("⏸ Сцена на паузе.")
    elif cmd in {"resume", "продолжить"}:
        if not scene.active:
            await message.reply("Нет активной сцены. <code>/rp start ...</code>")
            return
        await RPStore.update(uid, cid, paused=False)
        await message.reply("▶️ Продолжаем.")
    elif cmd in {"stop", "стоп", "end"}:
        await RPStore.update(uid, cid, active=False, paused=False)
        await message.reply("🛑 Сцена завершена. Персонажи и мир сохранены, новая сцена — <code>/rp start</code>.")
    elif cmd in {"undo", "откат"}:
        if not scene.turns:
            await message.reply("Откатывать нечего.")
            return
        await RPStore.update(uid, cid, turns=scene.turns[:-1], turn_count=max(0, scene.turn_count - 1))
        await message.reply("↩️ Последний ход отменён.")
    elif cmd in {"retry", "заново"}:
        if not (scene.active and scene.turns):
            await message.reply("Нет хода для переписывания.")
            return
        last = scene.turns[-1]["u"]
        scene = await RPStore.update(uid, cid, turns=scene.turns[:-1], turn_count=max(0, scene.turn_count - 1))
        await _play(message, scene, last, retry=True)
    elif cmd in {"recap", "итог"}:
        text = scene.summary or "\n".join(f"• {t['u'][:120]}" for t in scene.turns[-5:]) or "Пока ничего не произошло."
        await message.reply(f"📜 <b>Ранее в сцене:</b>\n{html.escape(text[-3500:])}")
    elif cmd in {"status", "статус"}:
        await message.reply(
            f"🎭 Сцена: {'активна' if scene.active else 'нет'}{' (пауза)' if scene.paused else ''}\n"
            f"Ходов: <b>{scene.turn_count}</b>\n"
            f"Кира: {html.escape(scene.bot_char or '—')}\nТы: {html.escape(scene.user_char or '—')}\n"
            f"Мир: {html.escape(scene.setting or '—')}\n18+: {'✅' if await _adult(message) else '❌ (/mature accept)'}"
        )
    else:
        await message.reply(HELP)


async def _in_scene(message: Message) -> bool:
    text = (message.text or "").strip()
    if not message.from_user or not text or text.startswith("/"):
        return False
    if message.chat.type != "private":
        reply = message.reply_to_message
        if not (reply and reply.from_user and reply.from_user.id == message.bot.id):
            return False
    scene = await RPStore.get(message.from_user.id, message.chat.id)
    return scene.active and not scene.paused


@router.message(_in_scene)
async def rp_continue(message: Message):
    scene = await RPStore.get(message.from_user.id, message.chat.id)
    await _play(message, scene, (message.text or "").strip())
