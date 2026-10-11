import html
import os
import os.path

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    InputMediaPhoto,
    FSInputFile,
    Message,
    CallbackQuery,
    MessageReactionUpdated,
    ReactionTypeEmoji,
)
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import log
from bot.config import settings
from bot.owners import is_owner, bind_owner
from bot.help_ui import admin_chat_keyboard, build_help_pages, help_url
from bot.bot import rp_manager
from bot.community_systems import ROLE_RANK, resolve_group_role, role_has_permission
from bot.core import (
    CommandManager,
    RPPageCB,
    fetch_user,
    max_per_page,
    start_create_character,
)
from bot.core_anime.anime import AnimeAPI
from bot.core_anime.filters import KiraAnimeFilter
from bot.downloader import Downloader, DownloadTooLarge
from bot.internet_tools import (
    InternetDownloadTooLarge,
    InternetDownloader,
    InternetError,
    InternetSearch,
    InvalidInternetURL,
    SearchError,
    UnsafeInternetURL,
)
from bot.errors import ErrorGetUser
from bot.fsm import SupportTicket
from bot.locale import _
from bot.media_downloader import MediaDownloadError, MediaTooLarge, media_downloader
from bot.pyrogram_core import PyroAPI
from bot.runtime import metrics
from bot.sql import (
    CharacterAlreadyMarried,
    CharacterManager,
    ChatManager,
    ClassManager,
    MarryMe,
    MarryYourself,
    RaceManager,
    RPTrigger,
    UserManager,
)
from bot.sql.errors import (
    CharacterNotMarried,
    SelfNotHaveCharacter,
    UserNotHaveCharacter,
)
from bot.sql.orm_tables import Class, Race

router = Router()
character_manager = CharacterManager()

cmd_manager = CommandManager()


def _read_owner_id() -> int | None:
    raw_owner_id = os.getenv("OWNER_ID", "").strip()
    if not raw_owner_id:
        return None
    if raw_owner_id.lstrip("-").isdigit():
        owner_id = int(raw_owner_id)
        return owner_id if owner_id > 0 else None
    log.warning("OWNER_ID имеет невалидное значение: %s", raw_owner_id)
    return None


OWNER_ID = _read_owner_id()


def _is_owner(user_id: int) -> bool:
    return is_owner(user_id)


async def _is_sudo_user(user_id: int) -> bool:
    return _is_owner(user_id) or await UserManager.is_sudo(user_id)


def _command_arg(message: Message) -> str | None:
    if not message.text:
        return None
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    value = parts[1].strip()
    return value if value else None


async def _ensure_sudo(message: Message) -> bool:
    if not message.from_user:
        return False
    if await _is_sudo_user(message.from_user.id):
        return True
    await message.reply(_("sudo_only"))
    return False


async def _extract_target_user_id(message: Message) -> int | None:
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user.id

    arg = _command_arg(message)
    if not arg:
        return None

    target = arg.rstrip(",")
    if target.lstrip("-").isdigit():
        return int(target)

    try:
        return await PyroAPI.get_entity_id(target)
    except ErrorGetUser:
        return None


@router.message(Command("claim_owner"))
async def claim_owner_handle(message: Message):
    if message.chat.type != "private" or not message.from_user:
        await message.reply("Напиши мне /claim_owner в личных сообщениях.")
        return
    username = (message.from_user.username or "").casefold()
    slot = next((number for number, name in ((2, "tishir22"), (3, "helis_pro1")) if username == name), None)
    if not slot:
        await message.reply("Этот аккаунт не указан в списке владельцев.")
        return
    await message.reply(f"🦊 Аккаунт @{username} проверен. Твой Telegram ID: <code>{message.from_user.id}</code>. Передай его главному владельцу: он закрепит роль командой <code>/owner_bind {slot} {message.from_user.id}</code>.")


@router.message(Command("owners"))
async def owners_handle(message: Message):
    if not message.from_user:
        return
    from bot.owners import _bindings
    bindings = _bindings()
    active = [f"{number}. @{name} — {'назначен' if str(number) in bindings else 'ждёт назначения'}"
              for number, name in ((2, 'tishir22'), (3, 'Helis_pro1'))]
    await message.reply("👑 <b>Владельцы Киры</b>\n1. Главный владелец\n" + "\n".join(active) +
                        "\n\nДля назначения: /claim_owner в личке, затем /owner_bind у главного владельца.")


@router.message(Command("owner_bind"))
async def owner_bind_handle(message: Message):
    if not message.from_user or message.from_user.id != settings.owner_id:
        await message.reply("Только главный владелец может вручную закрепить ID.")
        return
    args = (message.text or "").split()
    if len(args) != 3 or args[1] not in {"2", "3"} or not args[2].isdigit():
        await message.reply("Формат: <code>/owner_bind 2 TELEGRAM_ID</code> или <code>/owner_bind 3 TELEGRAM_ID</code>.")
        return
    await message.reply(await bind_owner(int(args[1]), int(args[2]), primary=True))


@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    race_manager = RaceManager()
    class_manager = ClassManager()
    await UserManager.get(message.from_user.id)
    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else ""

    if payload == "new_character":
        await start_create_character(message, state, message.from_user)
        return
    elif payload == "support":
        await state.set_state(SupportTicket.waiting_question)
        await message.answer(
            "🛟 <b>Поддержка Kira</b>\n"
            "Напиши вопрос одним сообщением. Я передам его в админ-чат вместе с твоим профилем.\n"
            "Можно отправить текст, фото, документ, видео или голосовое с подписью."
        )
        return
    elif payload.startswith("help"):
        raw_chat = payload[4:].strip()
        if not raw_chat.isdigit():
            await _send_help(message, admin=_is_owner(message.from_user.id))
            return
        try:
            member = await message.bot.get_chat_member(-int(raw_chat), message.from_user.id)
            is_admin = member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
        except Exception:
            is_admin = False
        await _send_help(message, admin=is_admin or _is_owner(message.from_user.id))
        return


    if message.chat.type == "private":
        character = await character_manager.get(message.from_user.id)
        text = _("new_character_btn") if not character else _("change_character_btn")
        builder.button(text=text, callback_data="new_character")
        if character:
            married = _(
                "married", married=character.married.name, user_id=character.married.user_id)\
                if character.married else " "
            caption = _(
                "user_character",
                name=character.name,
                race=(await race_manager.get_by_id(character.race_id)).name,
                character_class=(await class_manager.get_by_id(character.class_id)).name,
                description=character.description,
                married=married
            )
        else:
            caption = _("user_no_character")
        me = await message.bot.get_me()
        builder.button(text="📚 Все команды", url=help_url() or f"https://t.me/{me.username}?start=help")
        builder.button(text="🛟 Поддержка", url=f"https://t.me/{me.username}?start=support")
        builder.adjust(1)
        await message.answer_photo(
            caption=_(
                "start_message",
                user=fetch_user(message.from_user),
                character=caption
            ),
            photo=FSInputFile(os.path.join("bot", "media", "start_banner.jpg")),
            reply_markup=builder.as_markup()
        )
    else:
        await message.reply(_("im_here"))

@cmd_manager.register("+рп", _("add_rp_description"), admin_only=True)
@router.message(F.text.lower().startswith("+рп"))
async def new_rp_handle(message: Message):
    if not message.from_user:
        return
    if message.chat.type == "private":
        await message.reply(_("group_only_rp_add"))
        return

    html_parts = message.html_text.split(maxsplit=1)
    text_parts = message.text.split(maxsplit=1)
    if len(html_parts) != 2 or len(text_parts) != 2:
        await message.reply(_("rp_no_args"))
        return

    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status == ChatMemberStatus.CREATOR:
        pass
    elif member.status == ChatMemberStatus.ADMINISTRATOR:
        if not member.can_change_info:
            await message.reply(_("can_change_info_permission_need"))
            return
    else:
        await message.reply(_("admin_only"))
        return

    args = html_parts[1].strip()
    plain_args = text_parts[1].strip()

    is_global = plain_args.lower().endswith(" global")
    if is_global:
        if not await _is_sudo_user(message.from_user.id):
            await message.reply(_("sudo_only"))
            return
        chat_id = 0
        args = args.rsplit(" ", 1)[0].rstrip()
        plain_args = plain_args.rsplit(" ", 1)[0].rstrip()
    else:
        chat_id = message.chat.id

    if args.count("#") != 1 or plain_args.count("#") != 1:
        await message.reply(_("rp_no_args"))
        return

    trigger, answer = args.split("#", 1)
    _, plain_answer = plain_args.split("#", 1)
    trigger = trigger.strip().lower()
    answer = answer.strip()
    plain_answer = plain_answer.strip()

    errors = []
    if len(plain_answer) > 100:
        errors.append(_("rp_too_long_answer"))
    elif len(plain_answer) < 5:
        errors.append(_("rp_too_short_answer"))

    if len(trigger) > 20:
        errors.append(_("rp_too_long_trigger"))
    elif len(trigger) < 2:
        errors.append(_("rp_too_short_trigger"))

    if errors:
        await message.reply(f" {_('and')} ".join(errors))
        return

    was_existing = await rp_manager.get_for_chat(trigger, chat_id) is not None
    new_rp = RPTrigger(
        trigger=trigger,
        answer=answer,
        chat_id=chat_id,
        type="action" if "{u2}" in answer else "emotion",
    )
    await rp_manager.new(new_rp)
    await message.reply(_("rp_changed") if was_existing else _("rp_added"))

@cmd_manager.register("-рп", _("remove_rp_description"), admin_only=True)
@router.message(F.text.lower().startswith("-рп"))
async def remove_rp_handle(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    args = message.text.split(maxsplit=1)
    sudo = await _is_sudo_user(user.id)

    if message.chat.type == "private" and not sudo:
        await message.reply(_("group_only_rp_remove"))
        return

    if len(args) != 2:
        await message.reply(_("delete_rp_no_arg"))
        return

    trigger_name = args[1].strip().lower()

    if message.chat.type == "private":
        target = await rp_manager.get_for_chat(trigger_name, 0)
        if not target:
            await message.reply(_("delete_rp_not_found"))
            return
    else:
        local_trigger = await rp_manager.get_for_chat(trigger_name, chat_id)
        global_trigger = await rp_manager.get_for_chat(trigger_name, 0)

        if local_trigger:
            member = await message.bot.get_chat_member(chat_id, user.id)
            if member.status != ChatMemberStatus.CREATOR:
                if member.status != ChatMemberStatus.ADMINISTRATOR or not member.can_change_info:
                    await message.reply(_("no_permission_delete_rp"))
                    return
            target = local_trigger
        elif global_trigger:
            if not sudo:
                await message.reply(_("no_permission_delete_rp_global"))
                return
            target = global_trigger
        else:
            await message.reply(_("delete_rp_not_found"))
            return

    try:
        await rp_manager.delete(target)
    except Exception:
        log.exception("Не удалось удалить RP-триггер %s", trigger_name)
        await message.reply(_("unknown_delete_rp_error"))
        return
    await message.reply(_("rp_deleted"))


@cmd_manager.register("+раса", _("add_race_description"), admin_only=True)
@router.message(F.text.lower().startswith("+раса"))
async def add_race_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    race_name = _command_arg(message)
    if not race_name:
        await message.reply(_("race_add_usage"))
        return

    if await RaceManager.get_by_name(race_name):
        await message.reply(_("race_already_exists", name=race_name))
        return

    await RaceManager.new(Race(name=race_name))
    await message.reply(_("race_added", name=race_name))


@cmd_manager.register("-раса", _("remove_race_description"), admin_only=True)
@router.message(F.text.lower().startswith("-раса"))
async def remove_race_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    race_name = _command_arg(message)
    if not race_name:
        await message.reply(_("race_remove_usage"))
        return

    race = await RaceManager.get_by_name(race_name)
    if not race:
        await message.reply(_("race_not_found", name=race_name))
        return

    await RaceManager.delete(race)
    await message.reply(_("race_deleted", name=race_name))


@cmd_manager.register("+класс", _("add_class_description"), admin_only=True)
@router.message(F.text.lower().startswith("+класс"))
async def add_class_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    class_name = _command_arg(message)
    if not class_name:
        await message.reply(_("class_add_usage"))
        return

    if await ClassManager.get_by_name(class_name):
        await message.reply(_("class_already_exists", name=class_name))
        return

    await ClassManager.new(Class(name=class_name))
    await message.reply(_("class_added", name=class_name))


@cmd_manager.register("-класс", _("remove_class_description"), admin_only=True)
@router.message(F.text.lower().startswith("-класс"))
async def remove_class_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    class_name = _command_arg(message)
    if not class_name:
        await message.reply(_("class_remove_usage"))
        return

    cl = await ClassManager.get_by_name(class_name)
    if not cl:
        await message.reply(_("class_not_found", name=class_name))
        return

    await ClassManager.delete(cl)
    await message.reply(_("class_deleted", name=class_name))


@cmd_manager.register("+судо", _("add_sudo_description"), admin_only=True)
@router.message(F.text.lower().startswith("+судо"))
async def add_sudo_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    target_id = await _extract_target_user_id(message)
    if target_id is None:
        await message.reply(_("sudo_usage"))
        return

    await UserManager.get(target_id)
    if await _is_sudo_user(target_id):
        await message.reply(_("sudo_already", user_id=target_id))
        return

    await UserManager.promote(target_id)
    await message.reply(_("sudo_added", user_id=target_id))


@cmd_manager.register("-судо", _("remove_sudo_description"), admin_only=True)
@router.message(F.text.lower().startswith("-судо"))
async def remove_sudo_handle(message: Message):
    if not await _ensure_sudo(message):
        return

    if not message.from_user:
        return

    target_id = await _extract_target_user_id(message)
    if target_id is None:
        await message.reply(_("sudo_usage"))
        return

    if target_id == message.from_user.id:
        await message.reply(_("sudo_cannot_remove_self"))
        return
    if _is_owner(target_id):
        await message.reply(_("sudo_cannot_remove_owner", user_id=target_id))
        return

    if not await UserManager.is_sudo(target_id):
        await message.reply(_("sudo_not_found", user_id=target_id))
        return

    await UserManager.demote(target_id)
    await message.reply(_("sudo_removed", user_id=target_id))

@cmd_manager.register("список рп", _("rp_list_description"))
@router.message(F.text.lower() == "список рп")
async def rp_list_cmd(message: Message):
    chat_id = message.chat.id
    chat_triggers = rp_manager.get_by_chat_id(chat_id)

    if not chat_triggers:
        # Используем эмодзи для настроения Хаттори
        await message.reply(f"🌸 {_('no_rp_here')}")
        return

    # Рассчитываем пагинацию
    rp_lens = [len(t.trigger) + len(t.answer) + 4 for t in chat_triggers]
    page_size = max_per_page(rp_lens)
    total_pages = (len(chat_triggers) + page_size - 1) // page_size

    first_page = chat_triggers[:page_size]

    header = _("rp_header") + "\n"

    items = []
    for t in first_page:
        items.append(f"<blockquote><b><code>{t.trigger}</code></b> — {t.answer}</blockquote>")

    content = "\n \n".join(items)


    full_text = f"{header}{content}"

    # --- Настройка клавиатуры ---
    builder = InlineKeyboardBuilder()
    if total_pages > 1:
        builder.button(text=f"1 / {total_pages}", callback_data="none") \
               .button(text="▶️ След.", callback_data=RPPageCB(page=2, total_pages=total_pages).pack()) \
               .adjust(2, repeat=True)

    await message.reply(full_text, reply_markup=builder.as_markup(), parse_mode="HTML")



@cmd_manager.register("сделать предложение", _("marry_description"))
@router.message(F.text.lower() == "сделать предложение")
async def marry_cmd(message: Message):
    user = message.from_user
    if message.chat.type == "private":
        return

    reply = message.reply_to_message
    if not reply:
        await message.reply(_("no_reply"))
        return
    reply = reply.from_user
    me = await message.bot.get_me()
    builder = InlineKeyboardBuilder()
    builder.button(text=_("new_character_btn"), url=f"https://t.me/{me.username}?start=new_character")
    try:
        await CharacterManager.premarry(user.id, reply.id, me.id)
    except CharacterAlreadyMarried:
        await message.reply(_("already_married"))
        return
    except MarryYourself:
        await message.reply(_("marry_yourself"))
        return
    except SelfNotHaveCharacter:
        await message.reply(_("self_not_have_character"), reply_markup=builder.as_markup())
        return
    except UserNotHaveCharacter:
        await message.reply(_("user_not_have_character"), reply_markup=builder.as_markup())
        return
    except MarryMe:
        await message.reply(_("marry_me"))
        return

    builder = InlineKeyboardBuilder()
    (
        builder.button(text=_("deny"), callback_data=f"deny:{reply.id}:{user.id}", icon_custom_emoji_id="5359379093823438704")
            .button(text=_("accept"), callback_data=f"accept:{reply.id}:{user.id}", icon_custom_emoji_id="5359746403721557595")
            .adjust(2)
    )
    await message.reply(
        _(
            "marry_request",
            user1=user.id,
            character1=(await character_manager.get(user.id)).name,
            user2=reply.id,
            character2=(await character_manager.get(reply.id)).name
        ),
        reply_markup=builder.as_markup()
    )

@cmd_manager.register("расстаться", _("unmarry_description"))
@router.message(F.text.lower() == "расстаться")
async def unmarry_cmd(message: Message):
    builder = InlineKeyboardBuilder()
    try:
        await character_manager.preunmarry(message.from_user.id)
    except CharacterNotMarried:
        await message.reply(_("not_marry"))
        return
    character = await character_manager.get(message.from_user.id)
    (
        builder.button(text=_("deny"), callback_data=f"unmarry-deny:{character.user_id}", icon_custom_emoji_id="5359379093823438704")
            .button(text=_("accept"), callback_data=f"unmarry-accept:{character.user_id}", icon_custom_emoji_id="5359746403721557595")
            .adjust(2)
    )

    await message.reply(
        text=_("unmarry_request",
               character1=character.name,
               character2=character.married.name,
               user1=character.user_id,
               user2=character.married.user_id
               ),
        reply_markup=builder.as_markup()
    )


@cmd_manager.register("персонаж", _("character_description"))
@router.message(F.text.lower() == "персонаж")
async def character_cmd(message: Message):
    user_id = message.from_user.id

    reply = message.reply_to_message
    builder = InlineKeyboardBuilder()
    me = await message.bot.get_me()
    target_user_id = user_id

    if reply:
        if reply.from_user.id == me.id:
            await message.reply(_("im_not_have_character"))
            return
        target_user_id = reply.from_user.id
        character = await CharacterManager.get(reply.from_user.id)

    else:
        character = await CharacterManager.get(user_id)
    if not character:
        builder.button(text=_("new_character_btn"), url=f"https://t.me/{me.username}?start=new_character")
        text = _("user_not_have_character") if reply else _("self_not_have_character")
        await message.reply(text, reply_markup=builder.as_markup())
        return

    user = await UserManager.get(target_user_id)
    married = _("married", married=character.married.name, user_id=character.married.user_id) if character.married else " "
    character_text = _(
        "user_character",
        name=character.name,
        race=(await RaceManager.get_by_id(character.race_id)).name,
        character_class=(await ClassManager.get_by_id(character.class_id)).name,
        description=character.description,
        married=married
    )
    await message.reply(
        f"{character_text}\n\n<b><i>Длина члена</i>: {user.penis_len:.2f} см</b>"
    )

@cmd_manager.register("бан", _("ban_description"), admin_only=True)
@cmd_manager.register("разбан", _("unban_description"), admin_only=True)
@router.message(F.text.lower().startswith(("бан", "разбан")))
async def ban_unban_handler(message: Message):
    chat_id = message.chat.id
    text = message.text.lower()
    is_unban = text.startswith("разбан")

    actor_role = await resolve_group_role(
        message.bot, chat_id, message.from_user.id, owner_id=OWNER_ID or 0
    )
    if not role_has_permission(actor_role, "ban"):
        await message.reply(_("admin_only"))
        return

    args = message.text.split()[1:]

    if args:
        raw_arg = args[0].rstrip(",")

        if raw_arg.isdigit():
            target_id = int(raw_arg)
        else:
            try:
                target_id = await PyroAPI.get_entity_id(raw_arg)
            except ErrorGetUser:
                await message.reply(_("error_get_user"))
                return
    elif message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    else:
        await message.reply(_("no_args"))
        return

    if _is_owner(target_id):
        await message.reply("🛡 Владельца Киры нельзя забанить через бота.")
        return
    target_role = await resolve_group_role(message.bot, chat_id, target_id, owner_id=OWNER_ID or 0)
    if actor_role != "owner" and target_role != "member" and ROLE_RANK.get(target_role, 0) >= ROLE_RANK.get(actor_role, 0):
        await message.reply("🛡 Нельзя модерировать участника с равной или более высокой ролью Киры.")
        return

    try:
        if is_unban:
            await message.bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
            action_key = "unbanned"
        else:
            await message.bot.ban_chat_member(chat_id, target_id)
            action_key = "banned"

        target = await message.bot.get_chat(target_id)
        await message.reply(_(action_key, user=fetch_user(target)))

    except TelegramForbiddenError:
        await message.reply(_("no_permission_bot"))
    except TelegramBadRequest as e:
        err_msg = e.message.lower()
        if "user is an administrator" in err_msg:
            await message.reply(_("user_is_admin"))
        elif "can't remove chat owner" in err_msg:
            await message.reply(_("user_is_owner"))
        elif "user_id_invalid" in err_msg:
            await message.reply(_("error_get_user"))
        else:
            print(f"Ошибка при {text.split()[0]}: {e.message}")

async def _help_is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    if _is_owner(message.from_user.id):
        return True
    if message.chat.type == "private":
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False


async def _send_help(message: Message, *, admin: bool | None = None) -> None:
    admin = await _help_is_admin(message) if admin is None else admin
    me = await message.bot.get_me()
    url = help_url()
    if url:
        builder = InlineKeyboardBuilder()
        builder.button(text="📚 Открыть справочник команд", url=url)
        builder.button(text="🛟 Поддержка", url=f"https://t.me/{me.username}?start=support")
        builder.adjust(1)
        await message.reply(
            "🦊 <b>Справочник Kira</b>\nКоманды, примеры и поиск по категориям открываются по кнопке ниже.",
            reply_markup=builder.as_markup(),
        )
        return
    pages = build_help_pages(admin=admin, legacy_commands=cmd_manager.commands)
    for index, page in enumerate(pages):
        markup = admin_chat_keyboard(bot_username=me.username, include_help=False) if index == len(pages) - 1 else None
        try:
            if index == 0:
                await message.reply(page, reply_markup=markup)
            else:
                await message.answer(page, reply_markup=markup)
        except TelegramBadRequest:
            # Last-resort safety net: even if Telegram changes HTML parsing rules,
            # /help must still answer instead of silently dying.
            plain = html.unescape(re.sub(r"<[^>]+>", "", page))
            if index == 0:
                await message.reply(plain, parse_mode=None, reply_markup=markup)
            else:
                await message.answer(plain, parse_mode=None, reply_markup=markup)


@router.message(Command("help"))
@router.message(Command("commands"))
@router.message(F.text.lower() == "помощь")
async def help_handle(message: Message):
    await _send_help(message)


async def _begin_support(message: Message, state: FSMContext) -> None:
    if message.chat.type != "private":
        me = await message.bot.get_me()
        builder = InlineKeyboardBuilder()
        builder.button(text="🛟 Открыть поддержку", url=f"https://t.me/{me.username}?start=support")
        await message.reply(
            "🛟 Поддержка работает в личке с Kira, чтобы твой вопрос не увидела вся беседа.",
            reply_markup=builder.as_markup(),
        )
        return
    await state.set_state(SupportTicket.waiting_question)
    await message.reply(
        "🛟 <b>Поддержка Kira</b>\n"
        "Напиши свой вопрос следующим сообщением. Я отправлю его в админ-чат с отметкой твоего аккаунта.\n\n"
        "Поддерживаются текст, фото, документы, видео и голосовые сообщения.\n"
        "Отмена: <code>/cancel_support</code>"
    )


@router.message(Command("support"))
@router.message(F.text.lower().in_({"поддержка", "админ чат kira", "админ чат киры"}))
async def support_handle(message: Message, state: FSMContext):
    await _begin_support(message, state)


@router.callback_query(F.data == "support:start")
async def support_button_handle(call: CallbackQuery, state: FSMContext):
    if call.message and call.message.chat.type != "private":
        me = await call.bot.get_me()
        builder = InlineKeyboardBuilder()
        builder.button(text="🛟 Открыть поддержку", url=f"https://t.me/{me.username}?start=support")
        await call.message.answer(
            "🛟 Обращения в поддержку принимаются в личке с Kira, чтобы вопрос не был виден всей беседе.",
            reply_markup=builder.as_markup(),
        )
        await call.answer("Открой личку с Kira")
        return
    await state.set_state(SupportTicket.waiting_question)
    if call.message:
        await call.message.answer(
            "🛟 <b>Поддержка Kira</b>\n"
            "Напиши вопрос следующим сообщением. Он уйдёт в админ-чат вместе с твоим именем, @username и ID.\n"
            "Отмена: <code>/cancel_support</code>"
        )
    await call.answer("Жду твой вопрос")


@router.message(Command("cancel_support"))
async def cancel_support_handle(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == SupportTicket.waiting_question.state:
        await state.clear()
        await message.reply("✅ Обращение в поддержку отменено.")
    else:
        await message.reply("Сейчас нет активного обращения в поддержку.")


def _is_support_chat(message: Message) -> bool:
    raw = (settings.support_chat_id or "@kira26481").strip()
    if raw.lstrip("-").isdigit():
        return message.chat.id == int(raw)
    expected = raw.lstrip("@").casefold()
    return bool(message.chat.username and message.chat.username.casefold() == expected)


@router.message(Command("support_reply"))
async def support_reply_handle(message: Message):
    if not message.from_user:
        return
    allowed = _is_owner(message.from_user.id)
    if not allowed and _is_support_chat(message):
        try:
            member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
            allowed = member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}
        except Exception:
            allowed = False
    if not allowed:
        await message.reply("Ответы поддержки доступны только администраторам чата поддержки.")
        return
    raw = _command_arg(message) or ""
    parts = raw.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.reply("Использование: <code>/support_reply USER_ID текст ответа</code>")
        return
    user_id = int(parts[0])
    answer = parts[1].strip()[:3500]
    if not answer:
        await message.reply("Текст ответа пуст.")
        return
    try:
        await message.bot.send_message(
            user_id,
            "🛟 <b>Ответ поддержки Kira</b>\n\n" + html.escape(answer),
        )
    except Exception as exc:
        await message.reply(f"Не удалось доставить ответ: <code>{html.escape(type(exc).__name__)}</code>")
        return
    await message.reply(f"✅ Ответ отправлен пользователю <code>{user_id}</code>.")


@cmd_manager.register("общий сбор", _("tag_admin_description"), admin_only=True)
@cmd_manager.register("админ-чат", _("admin_chat_description"), admin_only=True)
@router.message(F.text.lower().startswith(("админ-чат", "общий сбор")))
async def tag_handle(message: Message):
    chat_id = message.chat.id
    actor_role = await resolve_group_role(
        message.bot, chat_id, message.from_user.id, owner_id=OWNER_ID or 0
    )
    if not role_has_permission(actor_role, "settings"):
        await message.reply(_("admin_only"))
        return

    if message.text.lower().startswith("общий сбор"):
        chat = await ChatManager.get(chat_id)
        if not chat:
            await ChatManager.upsert(chat_id)
            chat = await ChatManager.get(chat_id)
        if not chat.admin_chat_id:
            await message.reply(_("null_admin_chat", chat_id=chat_id))
            return

        admins = await message.bot.get_chat_administrators(chat_id)
        fetch_admins = [fetch_user(user.user) for user in admins if not user.user.is_bot]

        await message.react([ReactionTypeEmoji(emoji="🫡")])
        await message.bot.send_message(
            chat_id=chat.admin_chat_id,
            text=_("tag_admins", admins=" ".join(fetch_admins))
        )
    else:
        args = message.text.split()[1:]
        if len(args) == 0 or not args[0].lstrip("-").isdigit():
            await message.reply(_("chat_id_need"))
            return

        await ChatManager.upsert(int(args[0]), chat_id)
        await message.reply(_("chat_connected"))


@cmd_manager.register("Реакция на ссылку TikTok", _("tiktok_reaction_description"))
@router.message_reaction()
async def download_on_reaction(reaction: MessageReactionUpdated, bot: Bot):
    emojis = [getattr(i, "emoji", None) for i in reaction.new_reaction]
    if not any(e in emojis for e in ["👀", "⚡"]):
        return
    is_audio = True if "⚡" in emojis else False
    message_id = reaction.message_id
    chat_id = reaction.chat.id
    text = await PyroAPI.get_message_text(message_id, chat_id)
    if not text:
        return

    downloader = Downloader()
    tiktok_url = downloader.extract_url(text)
    if not tiktok_url:
        return

    action = "upload_document" if is_audio else "upload_video"

    try:
        async with ChatActionSender(action=action, chat_id=reaction.chat.id, bot=bot):
            file_data = await downloader.download(tiktok_url, is_audio=is_audio)

            if not file_data or not file_data.buffer:
                log.warning("TikTok download returned no data for %s", tiktok_url)
                await bot.send_message(chat_id, _("error_download"))
                return

            caption = _(
                "downloaded_caption",
                author=html.escape(file_data.author),
                title=html.escape(file_data.title),
                link=html.escape(tiktok_url, quote=True),
            )

            safe_author = "".join(
                ch for ch in file_data.author if ch.isalnum() or ch in "._-"
            )[:64] or "tiktok"
            file_buffer = BufferedInputFile(
                file_data.buffer.getvalue(),
                filename=f"{safe_author}.{file_data.ext}",
            )

            if is_audio:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=file_buffer,
                    caption=caption,
                    title=file_data.title,
                    performer=file_data.author,
                    duration=file_data.duration or None,
                )
            else:
                await bot.send_video(
                    chat_id=chat_id,
                    video=file_buffer,
                    caption=caption,
                    duration=file_data.duration or None,
                    supports_streaming=True,
                )
    except DownloadTooLarge:
        await bot.send_message(chat_id, _("error_download_too_large"))
    except Exception:
        log.exception("TikTok reaction download failed for %s", tiktok_url)
        await bot.send_message(chat_id, _("error_download"))


@cmd_manager.register("найди / /search", _("web_search_description"))
@router.message(Command("search"))
@router.message(F.text.regexp(r"(?i)^(?:найди|поиск)(?:\s|$)"))
async def web_search_handle(message: Message):
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) == 2 else ""
    if not query:
        await message.reply(_("web_search_usage"))
        return

    lower = query.lower()
    mode = "web"
    for prefix, kind in (
        ("видео ", "video"), ("video ", "video"),
        ("музыку ", "audio"), ("музыка ", "audio"), ("music ", "audio"),
        ("картинку ", "image"), ("картинки ", "image"), ("фото ", "image"), ("изображение ", "image"), ("image ", "image"),
    ):
        if lower.startswith(prefix):
            query = query[len(prefix):].strip()
            mode = kind
            break

    display_query = html.escape(query[:500])
    metrics.searches += 1
    waiting = await message.reply(_("web_search_wait", query=display_query))
    try:
        searcher = InternetSearch()
        if mode == "image":
            images = await searcher.image_search(query, max_results=4)
            if not images:
                await waiting.edit_text(_("web_search_no_results"))
                return
            media = [InputMediaPhoto(media=item.image_url, caption=(f"🖼 <b>{html.escape(query)}</b>" if i == 0 else None)) for i, item in enumerate(images)]
            try:
                await message.answer_media_group(media)
                await waiting.delete()
            except Exception:
                lines=[f"🖼 <b>Картинки по запросу:</b> {display_query}"]
                for i,item in enumerate(images,1):
                    lines.append(f"\n{i}. <a href=\"{html.escape(item.source_url or item.image_url, quote=True)}\">{html.escape(item.title[:120])}</a>")
                await waiting.edit_text("\n".join(lines), disable_web_page_preview=True)
            return

        if mode in {"video", "audio"}:
            rows = await media_downloader.search(query, limit=5)
            if not rows:
                await waiting.edit_text(_("web_search_no_results"))
                return
            first = rows[0]
            media = await media_downloader.download(first["url"], audio_only=(mode == "audio"))
            caption = f"{'🎵' if mode == 'audio' else '🎬'} <b>{html.escape(media.title[:700])}</b>\nПоиск: <b>{display_query}</b>"
            if media.uploader:
                caption += f"\nАвтор: {html.escape(str(media.uploader)[:180])}"
            file = FSInputFile(media.path, filename=media.path.name)
            if mode == "audio":
                await message.reply_audio(file, caption=caption)
            else:
                try:
                    await message.reply_video(file, caption=caption, supports_streaming=True)
                except TelegramBadRequest:
                    await message.reply_document(file, caption=caption)
            suggestions=[f"<b>Ещё результаты:</b>"]
            for idx,item in enumerate(rows[1:5], start=2):
                suggestions.append(f"{idx}. <a href=\"{html.escape(str(item.get('url','')), quote=True)}\">{html.escape(str(item.get('title','Без названия'))[:140])}</a>")
            if len(suggestions) > 1:
                await message.reply("\n".join(suggestions), disable_web_page_preview=True)
            await waiting.delete()
            try:
                media.cleanup()
            except Exception:
                pass
            return

        results = await searcher.search(query, max_results=6)
        if not results:
            await waiting.edit_text(_("web_search_no_results"))
            return

        chunks = []
        running_length = 0
        for index, result in enumerate(results, 1):
            raw_title = (result.title or result.url).strip()
            if len(raw_title) > 180:
                raw_title = raw_title[:177].rstrip() + "..."
            if len(result.url) > 1200:
                continue
            title = html.escape(raw_title)
            url = html.escape(result.url, quote=True)
            snippet = html.escape((result.snippet or "").strip())
            if len(snippet) > 220:
                snippet = snippet[:217].rstrip() + "..."
            item = f'• <a href="{url}"><b>{index}. {title}</b></a>'
            if snippet:
                item += f"\n  {snippet}"
            if running_length + len(item) > 3300:
                break
            chunks.append(item)
            running_length += len(item) + 2

        if not chunks:
            await waiting.edit_text(_("web_search_no_results"))
            return
        answer = _("web_search_results", query=display_query, results="\n\n".join(chunks))
        await waiting.edit_text(answer, disable_web_page_preview=True)
    except SearchError:
        log.exception("Internet search failed for query %r", query)
        await waiting.edit_text(_("web_search_failed"))
    except (MediaDownloadError, MediaTooLarge) as exc:
        log.warning("Rich search media failed for %r: %s", query, exc)
        await waiting.edit_text(_("web_download_failed"))
    except Exception:
        log.exception("Unexpected internet search error for query %r", query)
        await waiting.edit_text(_("web_search_failed"))


@cmd_manager.register("скачай / /download", _("web_download_description"))
@router.message(Command("download"))
@router.message(F.text.regexp(r"(?i)^(?:скачай|скачать)(?:\s|$)"))
async def web_download_handle(message: Message):
    """Универсальная загрузка: сначала media extractor, затем прямой HTTP-файл.

    Для «скачай аудио ...» yt-dlp извлекает аудиодорожку. Если URL не является
    поддерживаемым медиа-сайтом, команда откатывается на безопасный потоковый
    HTTP downloader из internet_tools.
    """
    downloader = InternetDownloader()
    source_text = message.text or ""
    url = downloader.extract_url(source_text)

    if not url and message.reply_to_message:
        reply = message.reply_to_message
        url = downloader.extract_url(reply.text or reply.caption or "")

    if not url:
        await message.reply(_("web_download_usage"))
        return

    lower = source_text.lower()
    audio_only = lower.startswith(("скачай аудио", "скачать аудио"))
    force_media = lower.startswith((
        "скачай видео", "скачать видео", "скачай аудио", "скачать аудио",
        "скачай медиа", "скачать медиа",
    ))

    metrics.downloads += 1
    waiting = await message.reply(_("web_download_wait"))
    downloaded = None
    media = None
    media_error: Exception | None = None
    try:
        # Media first is useful for YouTube/Instagram/X/Reddit/TikTok/etc.
        # For an ordinary file yt-dlp may reject the URL, then direct download is used.
        try:
            media = await media_downloader.download(url, audio_only=audio_only)
            caption = f"{'🎵' if audio_only else '🎬'} <b>{html.escape(media.title[:700])}</b>"
            if media.uploader:
                caption += f"\nАвтор: {html.escape(media.uploader[:180])}"
            input_file = FSInputFile(media.path, filename=media.path.name)
            if audio_only:
                await message.reply_audio(input_file, caption=caption)
            else:
                try:
                    await message.reply_video(input_file, caption=caption, supports_streaming=True)
                except TelegramBadRequest:
                    await message.reply_document(input_file, caption=caption)
            try:
                await waiting.delete()
            except TelegramBadRequest:
                pass
            return
        except MediaTooLarge:
            raise InternetDownloadTooLarge()
        except (MediaDownloadError, InternetError, UnsafeInternetURL, InvalidInternetURL) as exc:
            media_error = exc
            if force_media:
                raise

        async with ChatActionSender(
            action="upload_document",
            chat_id=message.chat.id,
            bot=message.bot,
        ):
            downloaded = await downloader.download(url)
            size_mb = downloaded.size / (1024 * 1024)
            caption = _(
                "web_download_done",
                filename=html.escape(downloaded.filename),
                size=f"{size_mb:.2f}",
                link=html.escape(downloaded.source_url, quote=True),
            )
            await message.reply_document(
                document=FSInputFile(downloaded.path, filename=downloaded.filename),
                caption=caption,
            )
        try:
            await waiting.delete()
        except TelegramBadRequest:
            pass
    except (InternetDownloadTooLarge, MediaTooLarge):
        limit_mb = downloader.max_bytes // (1024 * 1024)
        await waiting.edit_text(_("web_download_too_large", limit=limit_mb))
    except UnsafeInternetURL:
        await waiting.edit_text(_("web_download_unsafe"))
    except InvalidInternetURL:
        await waiting.edit_text(_("web_download_usage"))
    except (InternetError, MediaDownloadError) as exc:
        log.warning("Universal download failed for %s: media=%s final=%s", url, media_error, exc)
        await waiting.edit_text(_("web_download_failed"))
    except Exception:
        log.exception("Unexpected universal download error for %s", url)
        await waiting.edit_text(_("web_download_failed"))
    finally:
        if downloaded is not None:
            downloaded.cleanup()
        if media is not None:
            media.cleanup()


@cmd_manager.register("Кира, что за аниме", _("anime_search_description"))
@router.message(KiraAnimeFilter())
async def anime_search(message: Message):
    api = AnimeAPI()
    reply = message.reply_to_message
    error_message = await api.check_quota_limit()
    if error_message:
        await message.reply(_(error_message))
        return
    if reply:
        if not reply.photo:
            await message.reply(_("reply_to_photo_need"))
            return
        photo = reply.photo[-1]
    else:
        if not message.photo:
            await message.reply(_("reply_to_photo_need"))
            return
        photo = message.photo[-1]
    file_id = photo.file_id
    m = await message.reply(_("anime_wait"))
    async with ChatActionSender.typing(message.chat.id, message.bot):
        file = await message.bot.get_file(file_id)
        file_path = file.file_path
        file_bytes = await message.bot.download_file(file_path)
        data = file_bytes.read()
        anime = await api.search(data)
        if not anime:
            await message.reply(_("anime_not_found"))
            return

    description = api.prepare_description(
	    anime.description,
	    _,
	    "anime_info",
	    name=anime.name,
	    episodes=anime.episodes,
	    episode=anime.episode,
	    status=anime.status,
	    similarity_percent=anime.similarity_percent,
	    fragment_time=anime.fragment_time
    )

    caption_info = _(
        "anime_info",
        name=anime.name,
        description=description,
        episodes=anime.episodes,
        episode=anime.episode,
        status=anime.status,
        similarity_percent=anime.similarity_percent,
        fragment_time=anime.fragment_time
    )
    async with ChatActionSender.upload_video(message.chat.id, message.bot):
        await message.reply_animation(
            animation=anime.video,
            caption=caption_info
        )
        await m.delete()