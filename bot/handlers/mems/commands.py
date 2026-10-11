import json
import random
from asyncio import sleep
from contextlib import suppress
from pathlib import Path

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReactionTypeEmoji
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core import fetch_user
from bot.locale import _
from bot.sql import ChatManager, MemManager

from ..commands import cmd_manager
from .fsm import AutoAdd

router = Router()
removed_ids_by_chat: dict[int, list[int]] = {}


async def ensure_chat(chat_id: int) -> None:
    chat = await ChatManager.get(chat_id)
    if not chat:
        await ChatManager.upsert(chat_id)


async def ensure_mem_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status == ChatMemberStatus.CREATOR:
        return True
    if member.status == ChatMemberStatus.ADMINISTRATOR and member.can_change_info:
        return True
    key = "can_change_info_permission_need" if member.status == ChatMemberStatus.ADMINISTRATOR else "admin_only"
    await message.reply(_(key))
    return False


@cmd_manager.register("мем", _("get_mem_description"))
@router.message(F.text.lower().in_(["мем", "кто я"]))
async def get_mem(message: Message):
    if message.chat.type == "private" or not message.from_user:
        return

    chat_id = message.chat.id
    await ensure_chat(chat_id)

    sticker_id = await MemManager.get_random_id(chat_id)
    if not sticker_id:
        await message.reply(_("no_mems"))
        return

    module_dir = Path(__file__).parent
    json_path = module_dir / "mem_messages.json"
    with open(json_path, "r", encoding="utf-8") as file:
        mem_messages = json.load(file)

    text_message = await message.reply(
        random.choice(mem_messages).format(user=fetch_user(message.from_user))
    )
    sticker_message = await message.reply_sticker(sticker_id)

    await sleep(100)
    for msg in (text_message, sticker_message, message):
        with suppress(Exception):
            await msg.delete()


@cmd_manager.register("+мем", _("new_mem_description"), admin_only=True)
@router.message(F.text.lower() == "+мем")
async def new_mem(message: Message, state: FSMContext):
    if message.chat.type == "private":
        return
    if not await ensure_mem_admin(message):
        return

    chat_id = message.chat.id
    reply = message.reply_to_message

    if reply:
        if reply.sticker:
            await ensure_chat(chat_id)
            await MemManager.add(chat_id, reply.sticker.file_id)
            await message.react([ReactionTypeEmoji(emoji="👍")])
        return

    current_state = await state.get_state()
    if current_state == AutoAdd.toggle.state:
        await state.clear()
        builder = InlineKeyboardBuilder()
        builder.button(text=_("autoclean_btn"), callback_data="autoclean")
        sent = await message.reply(_("autoadd_off"), reply_markup=builder.as_markup())
        removed_ids_by_chat.setdefault(chat_id, []).extend([sent.message_id, message.message_id])
        return

    await state.set_state(AutoAdd.toggle)
    await state.set_data({"chat_id": chat_id})
    sent = await message.reply(_("autoadd_on"))
    removed_ids_by_chat[chat_id] = [sent.message_id, message.message_id]


@router.callback_query(lambda c: c.data == "autoclean")
async def autoclean_call(call: CallbackQuery):
    if not call.message or not isinstance(call.message, Message):
        return

    chat_id = call.message.chat.id
    message_ids = removed_ids_by_chat.pop(chat_id, [])
    for message_id in message_ids:
        with suppress(Exception):
            await call.bot.delete_message(chat_id=chat_id, message_id=message_id)

    await call.answer()


@router.message(AutoAdd.toggle, F.sticker)
async def autoadd_handle(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id:
        return

    chat_id = message.chat.id
    await ensure_chat(chat_id)
    await MemManager.add(chat_id, message.sticker.file_id)
    removed_ids_by_chat.setdefault(chat_id, []).append(message.message_id)
    await message.react([ReactionTypeEmoji(emoji="👍")])


@cmd_manager.register("мемы", _("total_mems_description"))
@router.message(F.text.lower() == "мемы")
async def mem_count_total(message: Message):
    if message.chat.type == "private":
        return

    chat_id = message.chat.id
    await ensure_chat(chat_id)
    total = len(await MemManager.list(chat_id))
    result = await message.reply(_("mem_count_total", total=total))

    await sleep(100)
    for msg in (result, message):
        with suppress(Exception):
            await msg.delete()
