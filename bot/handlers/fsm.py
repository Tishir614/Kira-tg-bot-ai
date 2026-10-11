from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import html
import time

from bot.fsm import CharacterCreation, SupportTicket
from bot.keyboards import gen_race_kb, gen_class_kb
from bot.locale import _
from bot.config import settings
from bot.sql import CharacterManager, RaceManager, ClassManager
from bot.sql.orm_tables import Character

router = Router()


async def _edit_fsm_message(event: Message | CallbackQuery, data: dict, text: str, *, reply_markup=None) -> None:
    """Edit the wizard message without storing aiogram Message objects in Redis."""
    bot = event.bot
    await bot.edit_message_text(
        chat_id=int(data["bot_chat_id"]),
        message_id=int(data["bot_message_id"]),
        text=text,
        reply_markup=reply_markup,
    )


@router.message(StateFilter(CharacterCreation.choosing_name))
async def process_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(_("text_only"))
        await message.delete()
        return
    if len(message.text) > 20:
        await message.answer(_("name_too_long"))
        await message.delete()
        return
    if len(message.text) < 2:
        await message.answer(_("name_too_short"))
        await message.delete()
        return

    data = await state.get_data()
    character = {"name": message.text}
    await _edit_fsm_message(
        message, data, _("set_race_character"),
        reply_markup=await gen_race_kb(message.from_user.id),
    )
    await state.update_data(character=character)
    await message.delete()
    await state.set_state(CharacterCreation.choosing_race)


@router.callback_query(
    StateFilter(CharacterCreation.choosing_race),
    lambda c: bool(c.data) and c.data.startswith("setrace+"),
)
async def process_race(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    character = dict(data.get("character") or {})
    character["race_id"] = int(call.data.split("+", 1)[1])
    await _edit_fsm_message(
        call, data, _("set_class_character"),
        reply_markup=await gen_class_kb(call.from_user.id),
    )
    await state.update_data(character=character)
    await state.set_state(CharacterCreation.choosing_class)
    await call.answer()


@router.callback_query(
    StateFilter(CharacterCreation.choosing_class),
    lambda c: bool(c.data) and c.data.startswith("setclass+"),
)
async def process_class(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    character = dict(data.get("character") or {})
    character["class_id"] = int(call.data.split("+", 1)[1])
    await _edit_fsm_message(call, data, _("set_description_character"))
    await state.update_data(character=character)
    await state.set_state(CharacterCreation.writing_description)
    await call.answer()


@router.message(StateFilter(CharacterCreation.writing_description))
async def process_description(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(_("text_only"))
        await message.delete()
        return
    if len(message.text) > 500:
        await message.answer(_("name_description_long", text=message.text))
        await message.delete()
        return
    if len(message.text) < 10:
        await message.answer(_("name_description_short", text=message.text))
        await message.delete()
        return

    data = await state.get_data()
    raw = dict(data.get("character") or {})
    raw["description"] = message.text
    raw["user_id"] = message.from_user.id
    character = Character(**raw)

    character_manager = CharacterManager()
    race_manager = RaceManager()
    class_manager = ClassManager()
    await character_manager.upsert(message.from_user.id, character)

    await message.bot.send_message(
        chat_id=int(data["bot_chat_id"]),
        text=_(
            "done_create_character",
            character=_(
                "user_character",
                name=character.name,
                race=(await race_manager.get_by_id(character.race_id)).name,
                character_class=(await class_manager.get_by_id(character.class_id)).name,
                description=character.description,
                married=" ",
            ),
        ),
    )
    await message.delete()
    await state.clear()


def _support_destination() -> int | str:
    raw = (settings.support_chat_id or "@kira26481").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw if raw.startswith("@") else "@" + raw


@router.message(StateFilter(SupportTicket.waiting_question))
async def process_support_question(message: Message, state: FSMContext):
    if not message.from_user:
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel_support"):
        await state.clear()
        await message.reply("✅ Обращение в поддержку отменено.")
        return

    body = (message.text or message.caption or "").strip()
    has_media = bool(
        message.photo
        or message.document
        or message.video
        or message.audio
        or message.voice
        or message.video_note
        or message.animation
        or message.sticker
    )
    if not body and not has_media:
        await message.reply(
            "Напиши вопрос текстом или отправь медиа. Для отмены: <code>/cancel_support</code>."
        )
        return

    user = message.from_user
    username = f"@{html.escape(user.username)}" if user.username else "без @username"
    question = html.escape(body[:3000]) if body else "[вопрос приложен медиа-сообщением]"
    ticket_id = f"K{int(time.time()) % 1_000_000:06d}-{user.id}"
    admin_text = (
        f"🛟 <b>Новое обращение {ticket_id}</b>\n"
        f"👤 <a href='tg://user?id={user.id}'>{html.escape(user.full_name)}</a>\n"
        f"🔗 {username} · <code>{user.id}</code>\n"
        f"💬 Чат пользователя: <code>{message.chat.id}</code>\n\n"
        f"<b>Вопрос:</b>\n{question}\n\n"
        f"Ответ пользователю: <code>/support_reply {user.id} текст ответа</code>"
    )

    destination = _support_destination()
    try:
        sent = await message.bot.send_message(
            destination,
            admin_text,
            disable_web_page_preview=True,
        )
        if has_media:
            try:
                await message.copy_to(destination, reply_to_message_id=sent.message_id)
            except Exception:
                pass
    except Exception as exc:
        await message.reply(
            "⚠️ Не удалось передать вопрос в поддержку. Убедись, что бот добавлен в админ-чат "
            "<code>@kira26481</code> и имеет право отправлять сообщения.\n"
            f"Код ошибки: <code>{html.escape(type(exc).__name__)}</code>"
        )
        return

    await state.clear()
    await message.reply(
        f"✅ <b>Вопрос отправлен в поддержку.</b>\nНомер: <code>{ticket_id}</code>\n"
        "Когда администратор ответит через Kira, ответ придёт сюда."
    )
