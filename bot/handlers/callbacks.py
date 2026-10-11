from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.bot import rp_manager
from bot.core import start_create_character, RPPageCB, max_per_page
from bot.locale import _
from bot.sql import (
    CharacterAlreadyMarried,
    CharacterManager,
    MarryYourself,
    SelfNotHaveCharacter,
    UserNotHaveCharacter,
)
from bot.sql.errors import CharacterNotMarried

router = Router()

@router.callback_query(F.data.startswith("new_character"))
async def process_new_character_call(call: CallbackQuery, state: FSMContext):
    await start_create_character(call.message, state, call.from_user)
    await call.answer()


@router.callback_query(RPPageCB.filter())
async def rp_pagination_handler(callback: CallbackQuery, callback_data: RPPageCB):
    chat_id = callback.message.chat.id
    chat_triggers = rp_manager.get_by_chat_id(chat_id) or []
    if not chat_triggers:
        await callback.answer("RP-команды больше недоступны.", show_alert=True)
        return
    page_size = max(1, max_per_page([len(t.trigger) + len(t.answer) + 4 for t in chat_triggers]))

    page = max(1, min(callback_data.page, callback_data.total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_triggers = chat_triggers[start:end]

    text = f"📜 RP-команды (стр. {page}/{callback_data.total_pages})\n\n" + \
           "\n".join(f"{t.trigger}: {t.answer}" for t in page_triggers)

    builder = InlineKeyboardBuilder()

    # Предыдущая (если не первая)
    if page > 1:
        builder.button(text="◀️ Пред.",
                       callback_data=RPPageCB(page=page - 1, total_pages=callback_data.total_pages).pack())

    builder.button(text=f"{page} / {callback_data.total_pages}", callback_data="none")

    # Следующая (если не последняя)
    if page < callback_data.total_pages:
        builder.button(text="▶️ След.",
                       callback_data=RPPageCB(page=page + 1, total_pages=callback_data.total_pages).pack())

    builder.adjust(3, repeat=True)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "none")
async def noop_callback(call: CallbackQuery):
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("accept:"))
@router.callback_query(lambda c: c.data.startswith("deny:"))
async def marry_call(call: CallbackQuery):
    action, target_id, requester_id = call.data.split(":")
    target_id = int(target_id)
    requester_id = int(requester_id)

    if call.from_user.id != target_id:
        await call.answer(_("not_for_you"), show_alert=True)
        return

    if action == "deny":
        await call.message.edit_text(_("deny_marry"))
        await call.answer()
        return

    me = await call.bot.get_me()
    try:
        await CharacterManager.premarry(requester_id, target_id, me.id)
        await CharacterManager.marry(requester_id, target_id)
    except CharacterAlreadyMarried:
        await call.message.edit_text(_("already_married"))
    except MarryYourself:
        await call.message.edit_text(_("marry_yourself"))
    except SelfNotHaveCharacter:
        await call.message.edit_text(_("self_not_have_character"))
    except UserNotHaveCharacter:
        await call.message.edit_text(_("user_not_have_character"))
    else:
        await call.message.edit_text(_("accept_marry"))
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("unmarry-"))
async def unmarry_call(call: CallbackQuery):
    action, raw_user_id = call.data.split("-", 1)[1].split(":", 1)
    user_id = int(raw_user_id)
    character = await CharacterManager.get(user_id)

    if not character or not character.married or not character.married_id:
        await call.answer(_("not_marry"), show_alert=True)
        return

    partner_user_id = character.married.user_id
    if call.from_user.id not in (user_id, partner_user_id):
        await call.answer(_("not_for_you"), show_alert=True)
        return

    if action == "deny":
        await call.message.edit_text(_("deny_unmarry"))
        await call.answer()
        return

    try:
        await CharacterManager.preunmarry(user_id)
        await CharacterManager.unmarry(user_id)
    except CharacterNotMarried:
        await call.message.edit_text(_("not_marry"))
    else:
        await call.message.edit_text(_("accept_unmarry"))
    await call.answer()
