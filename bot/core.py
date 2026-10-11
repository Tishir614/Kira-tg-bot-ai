from __future__ import annotations

from typing import Callable, Dict

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import User, ChatFullInfo, Message

from bot.fsm import CharacterCreation
from bot.locale import _

class RPPageCB(CallbackData, prefix="rp"):
    page: int
    total_pages: int

def fetch_user(user: User | ChatFullInfo) -> str:
    if user.username:
        return "@"+user.username
    return f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

async def start_create_character(message: Message, state: FSMContext, user: User):
    user_id = user.id
    if message.chat.type != "private":
        await message.answer(_("private_only"))
        return
    m = await message.answer(_("set_name_character"))
    await message.delete()
    await state.update_data(
        user_id=user_id,
        bot_message_id=m.message_id,
        bot_chat_id=m.chat.id,
    )
    await state.set_state(CharacterCreation.choosing_name)

def max_per_page(lens: list[int]) -> int:
    if not lens:
        return 0
    total = 0
    count = 0
    for length in lens:
        if total + length > 4096:
            break
        total += length
        count += 1
    return count

class BotCommand:
    def __init__(self, name: str, description: str, admin_only: bool):
        self.name: str = name
        self.description: str = description
        self.admin_only: bool = admin_only

class CommandManager:
    def __init__(self):
        self.commands: Dict[str, BotCommand] = {}

    def register(self, name: str, description: str, admin_only: bool = False):
        def wrapper(func: Callable):
            self.commands[name] = BotCommand(name, description, admin_only)
            return func
        return wrapper

    def gen_help_message(self, admin: bool = False) -> str:
        def format_list(cmds_dict):
            return "\n".join([
                f"[ <code><b>{name}</b></code> ]:\n<blockquote>{cmd.description}</blockquote>"
                for name, cmd in cmds_dict.items()
            ])
        user_cmds = {n: c for n, c in self.commands.items() if not c.admin_only}
        help_text = _("help_message", commands=format_list(user_cmds))
        if admin:
            admin_cmds = {n: c for n, c in self.commands.items() if c.admin_only}
            admin_block = _("admin_commands", commands=format_list(admin_cmds))
            help_text += f"\n\n{admin_block}"
        return help_text