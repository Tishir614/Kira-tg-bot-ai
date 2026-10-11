from __future__ import annotations

import html
import secrets
import time
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import log
from bot.internet_tools import InternetDownloader, InternetSearch
from bot.media_downloader import MediaDownloadError, MediaTooLarge, media_downloader
from bot.social_media import SocialMediaError, SocialMediaInfo, detect_platform, social_media
from bot.sql import ChatSpeechManager

router = Router(name="kira-media-social")


@dataclass(slots=True)
class SearchSession:
    user_id: int
    kind: str
    rows: list[dict]
    created_at: float


_SEARCHES: dict[str, SearchSession] = {}
_SEARCH_TTL = 15 * 60


def _arg(message: Message) -> str:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _cleanup_searches() -> None:
    now = time.monotonic()
    for key in list(_SEARCHES):
        if now - _SEARCHES[key].created_at > _SEARCH_TTL:
            _SEARCHES.pop(key, None)


def _put_search(user_id: int, kind: str, rows: list[dict]) -> str:
    _cleanup_searches()
    token = secrets.token_hex(4)
    _SEARCHES[token] = SearchSession(user_id=user_id, kind=kind, rows=rows[:8], created_at=time.monotonic())
    return token


def _human_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _compact_number(value: int | None) -> str:
    if not value:
        return ""
    value = int(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


async def _is_admin(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


@router.message(Command("profanity"))
async def profanity_cmd(message: Message) -> None:
    raw = _arg(message).casefold()
    aliases = {
        "выкл": "clean", "чисто": "clean", "без": "clean", "off": "clean", "clean": "clean",
        "умеренно": "natural", "естественно": "natural", "обычно": "natural", "natural": "natural",
        "вкл": "free", "свободно": "free", "жестко": "free", "жёстко": "free", "on": "free", "free": "free",
    }
    if raw:
        if not await _is_admin(message):
            await message.reply("В группе менять режим речи Киры может администратор.")
            return
        target = aliases.get(raw)
        if not target:
            await message.reply("Использование: <code>/мат выкл|умеренно|вкл</code>")
            return
        await ChatSpeechManager.set(message.chat.id, target)
    current = await ChatSpeechManager.get(message.chat.id)
    labels = {"clean": "без мата", "natural": "естественный", "free": "свободный"}
    await message.reply(
        "🗯 <b>Речь Киры</b>\n"
        f"Режим: <b>{labels.get(current, current)}</b>\n\n"
        "<code>/мат выкл</code> — без нецензурной лексики\n"
        "<code>/мат умеренно</code> — иногда по контексту\n"
        "<code>/мат вкл</code> — можно говорить прямо и материться естественно\n\n"
        "Этот режим меняет стиль речи, но не отключает приватность, антиспам и защиту сервера."
    )


async def _search_media(message: Message, query: str, kind: str) -> None:
    if not message.from_user:
        return
    query = " ".join(query.split()).strip()
    if not query:
        samples = {
            "video": "/найти_видео funny fox animation",
            "audio": "/найти_музыку название трека",
            "image": "/найти_картинку ночной город",
        }
        await message.reply(f"Пример: <code>{samples[kind]}</code>")
        return
    wait = await message.reply("🔎 Ищу варианты…")
    try:
        if kind == "image":
            found = await InternetSearch().image_search(query, max_results=6)
            rows = [
                {"title": x.title or query, "url": x.image_url, "source_url": x.source_url, "platform": "image"}
                for x in found
            ]
        else:
            rows = await media_downloader.search(query, limit=6)
        if not rows:
            await wait.edit_text("Ничего подходящего не нашла.")
            return
        token = _put_search(message.from_user.id, kind, rows)
        action = {"video": "v", "audio": "a", "image": "i"}[kind]
        buttons: list[list[InlineKeyboardButton]] = []
        lines = [f"🔎 <b>{html.escape(query[:300])}</b>"]
        for idx, row in enumerate(rows, 1):
            title = html.escape(str(row.get("title") or "Без названия")[:160])
            url = html.escape(str(row.get("source_url") or row.get("url") or ""), quote=True)
            duration = _human_duration(row.get("duration"))
            lines.append(f"\n{idx}. <a href=\"{url}\">{title}</a>{' · ' + duration if duration else ''}")
            label = "🖼" if kind == "image" else ("🎵" if kind == "audio" else "🎬")
            buttons.append([InlineKeyboardButton(text=f"{label} Скачать №{idx}", callback_data=f"kms:{token}:{idx-1}:{action}")])
        await wait.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.exception("media search failed")
        await wait.edit_text("Не удалось выполнить поиск: " + html.escape(str(exc)[:250]))


@router.message(Command("media_video"))
async def media_video_cmd(message: Message) -> None:
    await _search_media(message, _arg(message), "video")


@router.message(Command("media_audio"))
async def media_audio_cmd(message: Message) -> None:
    await _search_media(message, _arg(message), "audio")


@router.message(Command("media_image"))
async def media_image_cmd(message: Message) -> None:
    await _search_media(message, _arg(message), "image")


@router.message(Command("media"))
async def media_cmd(message: Message) -> None:
    query = _arg(message)
    if not query:
        await message.reply(
            "📦 <b>Поиск и скачивание</b>\n"
            "<code>/найти_видео запрос</code>\n"
            "<code>/найти_музыку запрос</code>\n"
            "<code>/найти_картинку запрос</code>\n\n"
            "После поиска выбери нужный результат кнопкой."
        )
        return
    # Keep the hub copyable: arbitrary queries are not embedded in callback data.
    await message.reply(
        f"Что искать по запросу <b>{html.escape(query[:300])}</b>?\n\n"
        f"🎬 <code>/найти_видео {html.escape(query[:250])}</code>\n"
        f"🎵 <code>/найти_музыку {html.escape(query[:250])}</code>\n"
        f"🖼 <code>/найти_картинку {html.escape(query[:250])}</code>",
    )


async def _send_download(callback: CallbackQuery, session: SearchSession, row: dict, action: str) -> None:
    if not callback.message:
        return
    url = str(row.get("url") or "")
    if action == "i":
        downloaded = None
        try:
            downloaded = await InternetDownloader().download(url)
            file = FSInputFile(downloaded.path, filename=downloaded.filename)
            try:
                await callback.message.answer_photo(file, caption=f"🖼 <b>{html.escape(str(row.get('title') or 'Картинка')[:700])}</b>")
            except Exception:
                await callback.message.answer_document(file, caption="🖼 Найденное изображение")
        finally:
            if downloaded:
                downloaded.cleanup()
        return

    media = None
    try:
        media = await media_downloader.download(url, audio_only=(action == "a"))
        file = FSInputFile(media.path, filename=media.path.name)
        caption = f"{'🎵' if action == 'a' else '🎬'} <b>{html.escape(media.title[:700])}</b>"
        if action == "a":
            await callback.message.answer_audio(file, caption=caption)
        else:
            try:
                await callback.message.answer_video(file, caption=caption, supports_streaming=True)
            except Exception:
                await callback.message.answer_document(file, caption=caption)
    finally:
        if media:
            media.cleanup()


@router.callback_query(F.data.startswith("kms:"))
async def media_choice_callback(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    try:
        _, token, raw_index, action = callback.data.split(":", 3)
        index = int(raw_index)
    except (ValueError, TypeError):
        await callback.answer("Неверная кнопка", show_alert=True)
        return
    _cleanup_searches()
    session = _SEARCHES.get(token)
    if not session or time.monotonic() - session.created_at > _SEARCH_TTL:
        await callback.answer("Поиск устарел. Запусти его ещё раз.", show_alert=True)
        return
    if callback.from_user.id != session.user_id:
        await callback.answer("Эта кнопка принадлежит автору поиска.", show_alert=True)
        return
    if index < 0 or index >= len(session.rows):
        await callback.answer("Результат больше недоступен.", show_alert=True)
        return
    await callback.answer("Скачиваю…")
    try:
        await _send_download(callback, session, session.rows[index], action)
    except MediaTooLarge:
        if callback.message:
            await callback.message.answer("Файл слишком большой для текущего лимита Telegram.")
    except Exception as exc:
        log.warning("media choice download failed: %s", exc)
        if callback.message:
            await callback.message.answer("Не удалось скачать этот результат. Возможно, источник требует вход или изменил формат.")


def _info_text(info: SocialMediaInfo) -> str:
    icon = {"youtube": "▶️", "tiktok": "🎵", "twitch": "🟣"}.get(info.platform, "🌐")
    lines = [f"{icon} <b>{html.escape(info.title)}</b>"]
    if info.uploader:
        lines.append("Автор: " + html.escape(info.uploader))
    if info.duration:
        lines.append("Длительность: " + _human_duration(info.duration))
    if info.is_live:
        lines.append("🔴 <b>Сейчас в эфире</b>")
    if info.view_count:
        lines.append("Просмотры: " + _compact_number(info.view_count))
    if info.like_count:
        lines.append("Лайки: " + _compact_number(info.like_count))
    lines.append(f'<a href="{html.escape(info.url, quote=True)}">Открыть источник</a>')
    return "\n".join(lines)


async def _platform_command(message: Message, platform: str) -> None:
    if not message.from_user:
        return
    value = _arg(message).strip()
    if not value:
        samples = {"youtube": "котики", "tiktok": "furry animation", "twitch": "имя_канала"}
        await message.reply(f"Использование: <code>/{ {'youtube':'ютуб','tiktok':'тикток','twitch':'твич'}[platform] } {samples[platform]}</code>")
        return
    is_url = value.startswith(("http://", "https://"))
    wait = await message.reply("⏳ Проверяю источник…")
    try:
        if is_url:
            info = await social_media.inspect(value)
            row = {"title": info.title, "url": info.url, "platform": platform}
            token = _put_search(message.from_user.id, "social", [row])
            buttons = []
            if not (platform == "twitch" and info.is_live):
                buttons.append([
                    InlineKeyboardButton(text="🎬 Скачать видео", callback_data=f"kms:{token}:0:v"),
                    InlineKeyboardButton(text="🎵 Скачать аудио", callback_data=f"kms:{token}:0:a"),
                ])
            await wait.edit_text(_info_text(info), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None, disable_web_page_preview=True)
            return

        if platform == "twitch" and re_full_twitch_name(value):
            try:
                info = await social_media.twitch_channel(value)
                await wait.edit_text(_info_text(info), disable_web_page_preview=True)
                return
            except SocialMediaError:
                # Offline channels often cannot be extracted as live streams; fall back
                # to public web search so the user still gets the channel/profile links.
                pass

        rows = await social_media.search(platform, value, limit=5)
        if not rows:
            await wait.edit_text("Ничего не найдено.")
            return
        token = _put_search(message.from_user.id, "social", rows)
        lines = [f"🔎 <b>{platform.title()}: {html.escape(value[:250])}</b>"]
        buttons: list[list[InlineKeyboardButton]] = []
        for idx, row in enumerate(rows, 1):
            url = str(row.get("url") or "")
            title = html.escape(str(row.get("title") or url)[:160])
            lines.append(f'\n{idx}. <a href="{html.escape(url, quote=True)}">{title}</a>')
            if platform == "youtube":
                buttons.append([
                    InlineKeyboardButton(text=f"🎬 №{idx}", callback_data=f"kms:{token}:{idx-1}:v"),
                    InlineKeyboardButton(text=f"🎵 №{idx}", callback_data=f"kms:{token}:{idx-1}:a"),
                ])
            elif platform == "tiktok":
                buttons.append([InlineKeyboardButton(text=f"📥 Скачать №{idx}", callback_data=f"kms:{token}:{idx-1}:v")])
        await wait.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.warning("%s integration failed: %s", platform, exc)
        await wait.edit_text("Не удалось получить данные. Ссылка может быть приватной, удалённой или требовать авторизацию.")


def re_full_twitch_name(value: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,32}", value))


@router.message(Command("youtube"))
async def youtube_cmd(message: Message) -> None:
    await _platform_command(message, "youtube")


@router.message(Command("tiktok"))
async def tiktok_cmd(message: Message) -> None:
    await _platform_command(message, "tiktok")


@router.message(Command("twitch"))
async def twitch_cmd(message: Message) -> None:
    await _platform_command(message, "twitch")

@router.message(Command("find_track"))
async def find_track_from_video(message: Message, bot: Bot) -> None:
    """Reply /трек to a video/audio/document to identify and verify the exact edit/remix."""
    from pathlib import Path
    import tempfile
    from bot.track_finder import TrackFinderError, track_finder

    src = message.reply_to_message
    media = None
    if src:
        media = src.video or src.audio or src.voice or src.document
    if not media:
        await message.answer("🎧 Ответь командой <b>/трек</b> на видео или аудиофайл. Я распознаю основу и отдельно проверю конкретный ремикс по акустическому отпечатку.")
        return
    if getattr(media, "file_size", 0) and media.file_size > 150 * 1024 * 1024:
        await message.answer("⚠️ Файл слишком большой. Пришли видео до 150 МБ.")
        return

    status = await message.answer("🎧 Слушаю несколько фрагментов и ищу именно эту версию трека…")
    suffix = Path(getattr(media, "file_name", "") or ".mp4").suffix or ".mp4"
    tmp = Path(tempfile.mkdtemp(prefix="kira_track_"))
    source = tmp / f"source{suffix}"
    match = None
    try:
        await bot.download(media, destination=source)
        match = await track_finder.identify(source)
        pct = round(match.confidence * 100)
        base = f"🎵 <b>{html.escape(match.title)}</b>\n👤 {html.escape(match.artist or 'Исполнитель не указан')}"
        if match.exact_version and match.downloaded:
            await status.edit_text(base + f"\n\n✅ Акустическое совпадение версии: <b>{pct}%</b>. Отправляю найденный вариант.")
            await message.answer_audio(FSInputFile(match.downloaded.path, filename=match.downloaded.path.name), caption=f"✅ Проверенная версия · совпадение {pct}%")
        elif match.url:
            await status.edit_text(base + f"\n\n🟡 Основа определена, но точное совпадение ремикса недостаточно сильное: <b>{pct}%</b>. Я не буду выдавать другой вариант за тот же самый.")
        else:
            await status.edit_text(base + "\n\n🟡 Основу трека нашла, но именно эту версию/ремикс в доступных результатах подтвердить не удалось.")
    except TrackFinderError as exc:
        await status.edit_text(f"❌ {html.escape(str(exc))}")
    except Exception as exc:
        log.exception("Track recognition failed: %s", exc)
        await status.edit_text("❌ Не удалось закончить распознавание. Проверь доступ к поиску и зависимости контейнера.")
    finally:
        if match and match.downloaded:
            match.downloaded.cleanup()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
