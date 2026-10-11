from __future__ import annotations

import re

# Russian commands are the public interface. Legacy English names are kept as
# compatibility targets, so upgrades never break old buttons, docs, or habits.
RUSSIAN_COMMAND_ALIASES: dict[str, str] = {
    "kira": "кира_мини",
    "boss": "босс",
    "effects": "эффекты",
    "kira_life": "жизнь_киры",
    "kira_world": "мир_киры",
    "pet": "питомец",
    "quest": "квест",
    "find_track": "трек",
    "achievements": "достижения",
    "activity": "активность",
    "admin_ai": "ии_админ",
    "ai": "ии",
    "ai_health": "здоровье_ии",
    "ai_providers": "провайдеры_ии",
    "ai_reset": "сброс_ии",
    "ai_speed": "скорость_ии",
    "aimod": "ии_модератор",
    "anniversary": "годовщина",
    "audio": "аудио",
    "avatar": "аватар",
    "backupdb": "бэкап_бд",
    "ban": "бан",
    "bio": "био",
    "birthday": "день_рождения",
    "blacklist": "черный_список",
    "campaign": "кампания",
    "cancel_support": "отменить_поддержку",
    "character_sheet": "лист_персонажа",
    "chatmood": "настроение_чата",
    "claim_owner": "стать_владельцем",
    "commands": "команды",
    "congrats": "поздравить",
    "crypto": "крипто",
    "currency": "валюта",
    "daily": "ежедневка",
    "delremind": "удалить_напоминание",
    "digest": "дайджест",
    "divorce": "развод",
    "dnd": "днд",
    "doctor": "диагностика",
    "download": "скачать",
    "event": "событие",
    "features": "возможности",
    "file": "файл",
    "find_memory": "найти_память",
    "findfile": "найти_файл",
    "fixtext": "исправить_текст",
    "forget_ai": "забыть_ии",
    "forget_me": "забыть_меня",
    "groupstats": "статистика_группы",
    "help": "помощь",
    "image": "картинка",
    "inventory": "инвентарь",
    "kick": "кик",
    "kira_app": "кира",
    "kira_chance": "шанс_киры",
    "kira_chat": "чат_киры",
    "kira_image": "кира_картинка",
    "kira_ref": "кира_референс",
    "lyrics": "текст_песни",
    "marriages": "браки",
    "marry": "брак",
    "mature": "взрослый_режим",
    "meme": "мем",
    "memory": "память",
    "modlog": "журнал_модерации",
    "music": "музыка",
    "mute": "мут",
    "myactivity": "моя_активность",
    "news": "новости",
    "owner_bind": "назначить_владельца",
    "owners": "владельцы",
    "pair": "пара",
    "pay": "перевести",
    "personality": "характер",
    "privacy": "приватность",
    "profile": "профиль",
    "recovery": "восстановление",
    "relationship": "отношения",
    "remember": "запомнить",
    "remind": "напомнить",
    "reminders": "напоминания",
    "report": "жалоба",
    "report_done": "закрыть_жалобу",
    "report_info": "жалоба_инфо",
    "report_reject": "отклонить_жалобу",
    "reports": "жалобы",
    "research": "исследование",
    "rewrite": "переписать",
    "richlist": "богачи",
    "role": "роль",
    "roll": "кубик",
    "rp18": "рп18",
    "rp18_actions": "рп18_действия",
    "rules": "правила",
    "search": "поиск",
    "shop": "магазин",
    "similar": "похожее",
    "songid": "узнать_трек",
    "spouse": "супруг",
    "staff": "команда_чата",
    "start": "старт",
    "status": "статус",
    "summary": "сводка",
    "summary_voice": "сводка_голоса",
    "support": "поддержка",
    "support_reply": "ответ_поддержки",
    "topic": "тема",
    "translate": "перевод",
    "tts": "озвучить",
    "ttsvoices": "голоса",
    "unban": "разбан",
    "unblacklist": "убрать_из_черного_списка",
    "unmute": "размут",
    "unrole": "снять_роль",
    "unwarn": "снять_пред",
    "video": "видео",
    "vision": "анализ_фото",
    "voice_ai": "голос_ии",
    "voice_auto": "автоголос",
    "wallet": "кошелек",
    "warn": "пред",
    "warnings": "предупреждения",
    "weather": "погода",
    "who": "кто",
    "work": "работа",
    "compliment": "комплимент",
    "dare": "действие",
    "duel": "дуэль",
    "my_nick": "мой_ник",
    "nick": "ник",
    "oracle": "оракул",
    "remove_nick": "удалить_ник",
    "truth": "правда",
    "profanity": "мат",
    "media": "медиа",
    "media_video": "найти_видео",
    "media_audio": "найти_музыку",
    "media_image": "найти_картинку",
    "youtube": "ютуб",
    "tiktok": "тикток",
    "twitch": "твич",
    "gender": "пол",
    "cosmetics": "косметика",
    "nick_color": "цвет_ника",
    "title": "титул",
    "badge": "значок",
    "profile_theme": "тема_профиля",
}

# Also accept familiar Latin transliterations for the short Telegram slash menu.
LATIN_MENU_ALIASES: dict[str, str] = {
    "komandy": "commands",
    "pomoshch": "help",
    "ii": "ai",
    "poisk": "search",
    "skachat": "download",
    "profil": "profile",
    "podderzhka": "support",
}

_RU_TO_LEGACY = {value.casefold(): key for key, value in RUSSIAN_COMMAND_ALIASES.items()}
_ALIAS_TO_LEGACY = _RU_TO_LEGACY | {key.casefold(): value for key, value in LATIN_MENU_ALIASES.items()}
_COMMAND_RE = re.compile(r"^/([^\s@]+)(@[A-Za-z0-9_]+)?(?=\s|$)", re.UNICODE)


def russian_name(legacy_name: str) -> str:
    return RUSSIAN_COMMAND_ALIASES.get(legacy_name, legacy_name)


def russian_usage(usage: str) -> str:
    """Translate only the first /command token, preserving arguments/examples."""
    if not usage.startswith("/"):
        return usage
    match = _COMMAND_RE.match(usage)
    if not match:
        return usage
    legacy = match.group(1)
    translated = russian_name(legacy)
    return f"/{translated}{match.group(2) or ''}{usage[match.end():]}"


def rewrite_command_text(text: str | None) -> str | None:
    """Rewrite /русская_команда to its legacy handler name before aiogram filters run."""
    if not text or not text.startswith("/"):
        return text
    match = _COMMAND_RE.match(text)
    if not match:
        return text
    target = _ALIAS_TO_LEGACY.get(match.group(1).casefold())
    if not target:
        return text
    return f"/{target}{match.group(2) or ''}{text[match.end():]}"
