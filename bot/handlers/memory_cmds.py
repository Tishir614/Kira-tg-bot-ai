from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import user_facts
from bot.image_styles import styles_help
from bot.sql import AssistantMemoryManager, ConversationSummaryManager, UserFactManager

router = Router(name="memory_cmds")


@router.message(Command("memory"))
@router.message(F.text.regexp(r"(?i)^память(?:\s|$)"))
async def memory_cmd(message: Message):
    if not message.from_user:
        return
    raw = re.sub(r"(?i)^(?:/memory(?:@\w+)?|память)\s*", "", message.text or "").strip()
    uid = message.from_user.id
    if raw.lower().startswith(("add ", "добавить ")):
        note = raw.split(maxsplit=1)[1].strip()[:user_facts.MAX_FACT_LEN]
        if len(note) < 3:
            await message.reply("Слишком коротко.")
            return
        await UserFactManager.remember(uid, [("note", note)])
        await message.reply("🧠 Запомнила.")
        return
    facts = await UserFactManager.list(uid)
    if not facts:
        await message.reply(
            "🧠 Я пока ничего о тебе не запомнила. Расскажи («меня зовут…», «я люблю…») "
            "или добавь вручную: <code>/memory add текст</code>. Забыть всё: <code>/forget</code>."
        )
        return
    labels = user_facts._LABELS
    lines = "\n".join(f"• {labels.get(k, k)}: {html.escape(v)}" for k, v in facts)
    await message.reply(f"🧠 <b>Что я о тебе помню</b>\n{lines}\n\nЗабыть всё: <code>/forget</code>")


@router.message(Command("forget"))
@router.message(F.text.regexp(r"(?i)^забудь\s+всё?(?:\s|$)"))
async def forget_cmd(message: Message):
    if not message.from_user:
        return
    await UserFactManager.forget(message.from_user.id)
    await AssistantMemoryManager.clear(message.from_user.id, message.chat.id)
    await ConversationSummaryManager.clear(message.from_user.id, message.chat.id)
    await message.reply("🧹 Забыла твои факты и историю нашего разговора здесь.")


@router.message(Command("styles"))
async def styles_cmd(message: Message):
    await message.reply(styles_help())
