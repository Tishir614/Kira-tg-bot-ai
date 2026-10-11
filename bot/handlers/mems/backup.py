from __future__ import annotations

import json
from asyncio import sleep

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import BufferedInputFile, Message

from bot.handlers.commands import cmd_manager
from bot.locale import _
from bot.sql import ChatManager, MemManager

router = Router()


async def ensure_chat(chat_id: int) -> None:
    chat = await ChatManager.get(chat_id)
    if not chat:
        await ChatManager.upsert(chat_id)


@cmd_manager.register("восстановить мемы", _("restore_description"), admin_only=True)
@router.message(F.text.lower() == "восстановить мемы")
async def restore_stickers(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return

    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != ChatMemberStatus.CREATOR:
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if not member.can_change_info:
                await message.reply(_("can_change_info_permission_need"))
                return
        else:
             await message.reply(_("admin_only"))
             return

    reply = message.reply_to_message
    if not reply or not reply.document:
        await message.reply(_("error_reply_need_file"))
        return

    file = await message.bot.get_file(reply.document.file_id)
    file_bytes: bytes = (await message.bot.download_file(file.file_path)).read()

    try:
        json_data = json.loads(file_bytes.decode("utf-8"))
        if not isinstance(json_data, list) or not all(isinstance(i, str) for i in json_data):
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        await message.reply(_("error_backup_file_read"))
        return

    chat_id = message.chat.id
    await ensure_chat(chat_id)

    existing_ids = {item.sticker_id for item in await MemManager.list(chat_id)}
    new_stickers = [sid for sid in json_data if sid not in existing_ids]

    if not new_stickers:
        await message.reply(_("zero_mems_restored"))
        return

    updated_stickers = await MemManager.add_many(chat_id, new_stickers)
    await message.reply(_("mem_database_restored", mems=len(updated_stickers)))


@cmd_manager.register("копия мемов", _("backup_description"), admin_only=True)
@router.message(F.text.lower() == "копия мемов")
async def backup_stickers(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return

    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != ChatMemberStatus.CREATOR:
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if not member.can_change_info:
                key = "can_change_info_permission_need"
            else:
                key = "admin_only"
        else:
            key = "admin_only"

        notice = await message.reply(_(key))
        await sleep(4)
        await message.delete()
        await notice.delete()
        return

    chat_id = message.chat.id
    await ensure_chat(chat_id)

    mems = await MemManager.list(chat_id)
    data = [item.sticker_id for item in mems]
    json_data = json.dumps(data, ensure_ascii=False, indent=2)

    await message.reply_document(
        BufferedInputFile(
            json_data.encode("utf-8"),
            filename="backup_mems.json",
        )
    )
