from __future__ import annotations

import html
import os
from urllib.parse import urlsplit
from collections.abc import Mapping
from typing import Any

from aiogram.types import BotCommand, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.command_aliases import russian_usage


def help_url() -> str | None:
    """HTTPS public address of the help site; never send a local URL to Telegram."""
    explicit = os.getenv("HELP_URL", "").strip()
    dnd = os.getenv("DND_WEBAPP_URL", "").strip()
    url = explicit or (dnd.rsplit("/", 1)[0] + "/commands" if dnd.endswith("/dnd") else "")
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname and parts.hostname not in {"example.com", "localhost", "127.0.0.1"}:
        return url
    return None


# Telegram's slash-menu stays intentionally compact. /help is the complete command index.
MAIN_MENU_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Открыть Kira"),
    ("komandy", "Все команды Киры"),
    ("ii", "Спросить ИИ Киру"),
    ("poisk", "Поиск в интернете"),
    ("skachat", "Скачать файл или медиа"),
    ("profil", "Профиль и экономика"),
    ("status", "Статус Киры"),
    ("podderzhka", "Написать в поддержку"),
)


PUBLIC_SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "🧠 AI и общение",
        (
            ("/ai <вопрос>", "осмысленный диалог с Kira; в личке можно писать и без /ai"),
            ("/ai_reset", "очистить память текущего AI-диалога"),
            ("/forget_ai", "алиас для полного сброса памяти AI в этом чате"),
            ("/ai_speed", "скорость, адаптивный маршрут, модели и контекст локального AI"),
            ("/profanity", "режим речи Киры: без мата / естественный / свободный"),
            ("/ai_health", "проверить работу локальной AI-модели"),
            ("/ai_providers", "показать настроенные AI-провайдеры"),
            ("/summary", "сделать краткое резюме текста или сообщения"),
            ("/translate", "перевести текст"),
            ("/tts <текст>", "озвучить текст"),
            ("/ttsvoices", "показать доступные голоса"),
            ("/voice_ai", "ответить голосом на голосовое сообщение"),
            ("/voice_auto", "настроить автоматические голосовые Kira"),
            ("/kira_chat", "настройки живого общения Kira в группе"),
            ("/kira_chance", "шанс инициативной реплики Kira"),
        ),
    ),
    (
        "🧠 Память Киры 1.0",
        (
            ("/memory", "показать, что Кира помнит о тебе"),
            ("/remember ключ = значение", "сохранить важный факт или предпочтение"),
            ("/privacy", "настройки памяти и приватности"),
            ("/forget_me confirm", "удалить сохранённую память о себе"),
            ("/find_memory <запрос>", "найти обсуждение в памяти чата"),
            ("/digest 24h", "сводка важных событий группы за период"),
            ("/summary_voice", "кратко пересказать голосовое сообщением в ответ"),
            ("/personality", "настроить характер Киры в чате"),
        ),
    ),
    (
        "🌐 Интернет и медиа",
        (
            ("/search <запрос>", "быстрый web-поиск"),
            ("/research <тема>", "более глубокое исследование по источникам"),
            ("/news <тема>", "свежие новости"),
            ("/weather <город>", "погода"),
            ("/currency", "курсы валют"),
            ("/crypto", "криптовалюты"),
            ("/download <URL>", "скачать файл или медиа по ссылке"),
            ("/media", "центр поиска и скачивания медиа"),
            ("/media_video <запрос>", "найти несколько видео и скачать выбранное"),
            ("/media_audio <запрос>", "найти музыку и скачать выбранный результат"),
            ("/media_image <запрос>", "найти изображение и скачать выбранное"),
            ("/youtube <запрос или URL>", "поиск, информация и загрузка YouTube"),
            ("/tiktok <запрос или URL>", "поиск, информация и загрузка публичного TikTok"),
            ("/twitch <канал или URL>", "поиск и статус Twitch; клипы/VOD по публичным ссылкам"),
            ("/video", "скачать видео"),
            ("/audio", "скачать аудио"),
            ("/music", "поиск музыки"),
            ("/lyrics", "короткий фрагмент текста песни"),
            ("/songid", "попытаться определить трек"),
            ("/similar", "найти похожую музыку"),
        ),
    ),
    (
        "🎨 Изображения и файлы",
        (
            ("/image <описание>", "сгенерировать изображение"),
            ("/avatar <описание>", "создать аватарку"),
            ("/meme <идея>", "создать мем"),
            ("/rewrite <текст>", "переписать текст красивее"),
            ("/fixtext <текст>", "исправить ошибки в тексте"),
            ("/congrats <кому/повод>", "сгенерировать поздравление"),
            ("/kira_image <описание>", "нарисовать Kira"),
            ("/kira_ref", "показать референс Kira"),
            ("/vision", "проанализировать изображение, если vision-модель настроена"),
            ("/file", "проанализировать прикреплённый файл"),
            ("/findfile", "поиск по содержимому файла"),
        ),
    ),
    (
        "👤 Профиль, экономика и события",
        (
            ("/profile", "расширенный профиль пользователя"),
            ("/nick <ник>", "задать ник Киры для этого чата; используется в RP и обращениях"),
            ("/my_nick", "показать ник, которым Кира тебя называет"),
            ("/remove_nick", "удалить ник этого чата; аргумент 'глобально' удаляет общий"),
            ("/gender", "указать пол профиля или скрыть его"),
            ("/cosmetics", "косметика за уровни и монеты"),
            ("/nick_color #FF66CC", "цвет ника/профиля в Mini App"),
            ("/title <текст>", "персональный титул профиля"),
            ("/badge ⭐", "выбрать купленный значок"),
            ("/profile_theme midnight", "тема единого Mini App"),
            ("/bio <текст>", "установить описание профиля"),
            ("/wallet", "кошелёк, кулдауны и стоимость инвентаря"),
            ("/work", "подработка раз в час: монеты + XP"),
            ("/pay <сумма>", "перевести игровые монеты ответом на сообщение"),
            ("/richlist", "топ богачей текущей беседы"),
            ("/daily", "ежедневная награда"),
            ("/shop", "магазин"),
            ("/inventory", "инвентарь"),
            ("/achievements", "достижения"),
            ("/birthday", "день рождения"),
            ("/anniversary", "годовщины"),
            ("/relationship", "отношения"),
            ("/event", "события"),
        ),
    ),
    (
        "💞 Сообщество и роли",
        (
            ("/marry", "сделать предложение пользователю"),
            ("/spouse", "показать свою пару"),
            ("/divorce", "расторгнуть брак"),
            ("/marriages", "браки в беседе"),
            ("/activity", "топ активности группы"),
            ("/myactivity", "твоя активность"),
            ("/groupstats", "статистика группы"),
            ("/who [роль/описание]", "случайный активный участник беседы"),
            ("/pair", "случайный дуэт из активных участников"),
            ("/topic", "тема или мини-задание для оживления беседы"),
            ("/chatmood", "быстрый пульс активности беседы"),
            ("/staff", "роли команды беседы"),
            ("/rules", "правила чата"),
            ("/report", "пожаловаться на сообщение"),
            ("/warnings", "посмотреть предупреждения"),
        ),
    ),
    (
        "🎉 Лисий досуг",
        (
            ("/truth", "случайный вопрос для игры «Правда»"),
            ("/dare", "безопасное смешное задание для чата"),
            ("/oracle", "игровое предсказание дня, стабильное до завтра"),
            ("/duel", "шуточная дуэль ответом на сообщение участника"),
            ("/compliment", "комплимент себе или участнику ответом на сообщение"),
        ),
    ),
    (
        "🐉 D&D и напоминания",
        (
            ("/dnd", "открыть D&D внутри единого Kira Mini App"),
            ("/character_sheet", "лист персонажа D&D"),
            ("/roll", "бросить кубик, например /roll 2d6+3"),
            ("/campaign", "кампании D&D"),
            ("/remind", "создать напоминание"),
            ("/reminders", "список напоминаний"),
            ("/delremind", "удалить напоминание"),
        ),
    ),
    (
        "🔞 Взрослые функции",
        (
            ("/mature", "настройки Mature Mode после подтверждения 18+"),
            ("/stats", "статистика бота за день/неделю/месяц (владелец)"),
            ("/persona", "выбрать характер Киры: нежная, дерзкая, цундере…"),
            ("/forget", "забыть всё, что Кира помнит о тебе и вашем разговоре"),
            ("/kira", "открыть мини-приложение Kira (нужен KIRA_WEBAPP_URL)"),
            ("/styles", "стили для /image: стиль:аниме, стиль:рандом"),
            ("/rp", "умный RP-модуль: сцены, персонажи, память, retry/undo"),
            ("/rp18", "взрослая RP-сессия между совершеннолетними"),
            ("/rp18_actions", "парные RP18-действия с подтверждением"),
        ),
    ),
    (
        "🩺 Система",
        (
            ("/start", "открыть стартовый экран Kira"),
            ("/kira_app", "открыть Kira Mini App"),
            ("/help", "полный каталог команд на сайте"),
            ("/commands", "открыть тот же каталог команд"),
            ("/owners", "посмотреть статус совладельцев"),
            ("/cancel_support", "отменить незавершённое обращение в поддержку"),
            ("/features", "краткий обзор возможностей"),
            ("/status", "состояние основных сервисов"),
            ("/doctor", "расширенная диагностика"),
            ("/recovery", "состояние механизма восстановления"),
            ("/support", "отправить вопрос команде поддержки"),
            ("/claim_owner", "владельцу №2 или №3 узнать свой Telegram ID для назначения"),
        ),
    ),
)


ADMIN_SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "🛡 Модерация и администрация",
        (
            ("/aimod", "настроить контекстную AI-модерацию"),
            ("/admin_ai", "управлять настройками чата естественным языком"),
            ("/warn", "выдать предупреждение"),
            ("/unwarn", "снять предупреждение"),
            ("/mute", "выдать мут"),
            ("/unmute", "снять мут"),
            ("/kick", "исключить пользователя"),
            ("/ban", "забанить пользователя"),
            ("/unban", "разбанить пользователя"),
            ("/blacklist", "добавить в blacklist"),
            ("/unblacklist", "убрать из blacklist"),
            ("/modlog", "журнал модерации"),
            ("/reports", "очередь жалоб"),
            ("/report_info", "детали жалобы"),
            ("/report_done", "закрыть жалобу"),
            ("/report_reject", "отклонить жалобу"),
            ("/role", "назначить роль команды"),
            ("/unrole", "снять роль команды"),
            ("/backupdb", "создать резервную копию базы"),
            ("/owner_bind 2|3 TELEGRAM_ID", "главному владельцу назначить ID совладельца"),
            ("/support_reply USER_ID <текст>", "ответить пользователю из чата поддержки"),
        ),
    ),
)


def telegram_menu_commands() -> list[BotCommand]:
    return [BotCommand(command=command, description=description) for command, description in MAIN_MENU_COMMANDS]


def admin_chat_keyboard(*, bot_username: str | None = None, include_help: bool = False) -> InlineKeyboardMarkup:
    """Compatibility name: the old admin-chat button is now a private support flow."""
    builder = InlineKeyboardBuilder()
    if bot_username:
        builder.button(text="🛟 Поддержка", url=f"https://t.me/{bot_username}?start=support")
    else:
        builder.button(text="🛟 Поддержка", callback_data="support:start")
    if include_help and bot_username:
        builder.button(text="📚 Все команды", url=f"https://t.me/{bot_username}?start=help")
    builder.adjust(1)
    return builder.as_markup()


def _section_text(title: str, commands: tuple[tuple[str, str], ...]) -> str:
    body = "\n".join(
        f"• <code>{html.escape(russian_usage(command))}</code> — {html.escape(description)}"
        for command, description in commands
    )
    return f"<b>{title}</b>\n{body}"


def build_help_pages(*, admin: bool = False, legacy_commands: Mapping[str, Any] | None = None) -> list[str]:
    """Return compact Telegram-safe help pages with every built-in command."""
    pages: list[str] = []
    intro = (
        "🦊 <b>Kira • Центр помощи</b>\n"
        "<blockquote>Основное меню специально короткое. Здесь собраны русские команды Киры и назначение каждой. Старые английские команды тоже продолжают работать.</blockquote>"
    )

    public_chunks = [PUBLIC_SECTIONS[:3], PUBLIC_SECTIONS[3:6], PUBLIC_SECTIONS[6:]]
    for index, chunk in enumerate(public_chunks, start=1):
        text = intro + "\n\n" if index == 1 else f"🦊 <b>Kira • Команды {index}/3</b>\n\n"
        text += "\n\n".join(_section_text(title, commands) for title, commands in chunk)
        pages.append(text)

    extra_blocks: list[str] = []
    if legacy_commands:
        public_legacy = [(name, cmd) for name, cmd in legacy_commands.items() if not getattr(cmd, "admin_only", False)]
        if public_legacy:
            body = "\n".join(
                f"• <code>{html.escape(str(name))}</code> — {html.escape(str(getattr(cmd, 'description', '')))}"
                for name, cmd in public_legacy
            )
            extra_blocks.append("<b>⌨️ Текстовые команды</b>\n" + body)

    if admin:
        extra_blocks.extend(_section_text(title, commands) for title, commands in ADMIN_SECTIONS)
        if legacy_commands:
            admin_legacy = [(name, cmd) for name, cmd in legacy_commands.items() if getattr(cmd, "admin_only", False)]
            if admin_legacy:
                body = "\n".join(
                    f"• <code>{html.escape(str(name))}</code> — {html.escape(str(getattr(cmd, 'description', '')))}"
                    for name, cmd in admin_legacy
                )
                extra_blocks.append("<b>🔧 Текстовые команды администрации</b>\n" + body)

    if extra_blocks:
        current = "🦊 <b>Kira • Дополнительные команды</b>\n\n"
        for block in extra_blocks:
            candidate = current + ("\n\n" if current else "") + block
            if len(candidate) > 3800 and len(current) > 80:
                pages.append(current)
                current = "🦊 <b>Kira • Продолжение</b>\n\n" + block
            else:
                current = candidate
        if current:
            pages.append(current)

    # Defensive split for translated/extended legacy descriptions.
    safe_pages: list[str] = []
    for page in pages:
        if len(page) <= 3900:
            safe_pages.append(page)
            continue
        lines = page.splitlines()
        current = ""
        for line in lines:
            candidate = current + ("\n" if current else "") + line
            if len(candidate) > 3900 and current:
                safe_pages.append(current)
                current = line
            else:
                current = candidate
        if current:
            safe_pages.append(current)
    return safe_pages
