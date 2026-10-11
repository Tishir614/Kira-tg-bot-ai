import asyncio
import io
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp


log = logging.getLogger(__name__)


class DownloadError(Exception):
    """Ошибка получения метаданных или медиафайла."""


class DownloadTooLarge(DownloadError):
    """Файл превышает безопасный лимит загрузки в память/Telegram."""


@dataclass(slots=True)
class DownloadedBuffer:
    buffer: io.BytesIO
    title: str
    author: str
    duration: int
    ext: str
    thumbnail: Optional[str] = None


class Downloader:
    """Загрузчик TikTok с основным и резервным API.

    TikWM используется как основной источник. Старый downloader.bot оставлен
    как fallback, чтобы временный сбой одного сервиса не ломал функцию целиком.
    """

    TIKWM_API_URL = "https://www.tikwm.com/api/"
    LEGACY_API_URL = "https://downloader.bot/api/tiktok/info"
    MAX_MEDIA_BYTES = 49 * 1024 * 1024
    _TIKTOK_URL_RE = re.compile(
        r"https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s<>\"]+",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        }
        self.timeout = aiohttp.ClientTimeout(total=90, connect=15, sock_read=45)

    @classmethod
    def extract_url(cls, text: str) -> str | None:
        if not text:
            return None
        match = cls._TIKTOK_URL_RE.search(text)
        if not match:
            return None
        # Telegram/пользователи нередко ставят знаки препинания сразу после URL.
        return match.group(0).rstrip(".,!?;:)]}'")

    @staticmethod
    def _safe_text(value: Any, fallback: str) -> str:
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value[:900]
        return fallback

    @staticmethod
    def _normalize_media_url(url: Any) -> str | None:
        if not isinstance(url, str) or not url.strip():
            return None
        url = url.strip()
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith(("http://", "https://")):
            return url
        return None

    async def _tikwm_info(
        self,
        session: aiohttp.ClientSession,
        url: str,
        is_audio: bool,
    ) -> dict[str, Any] | None:
        try:
            async with session.post(
                self.TIKWM_API_URL,
                data={"url": url, "hd": "1"},
                headers=self.headers,
            ) as response:
                if response.status != 200:
                    log.warning("TikWM metadata HTTP %s", response.status)
                    return None
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            log.warning("TikWM metadata error: %s", exc)
            return None

        if not isinstance(payload, dict) or payload.get("code") != 0:
            log.warning("TikWM rejected TikTok URL: %r", payload)
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        if is_audio:
            music_info = data.get("music_info") if isinstance(data.get("music_info"), dict) else {}
            media_url = self._normalize_media_url(data.get("music") or music_info.get("play"))
        else:
            media_url = self._normalize_media_url(
                data.get("hdplay") or data.get("play") or data.get("wmplay")
            )

        if not media_url:
            return None

        author_data = data.get("author")
        if isinstance(author_data, dict):
            author = (
                author_data.get("unique_id")
                or author_data.get("nickname")
                or author_data.get("name")
            )
        else:
            author = author_data

        duration = data.get("duration")
        try:
            duration = int(duration or 0)
        except (TypeError, ValueError):
            duration = 0

        return {
            "media_url": media_url,
            "title": self._safe_text(data.get("title"), "TikTok"),
            "author": self._safe_text(author, "TikTok"),
            "duration": max(duration, 0),
            "thumbnail": self._normalize_media_url(data.get("cover")),
        }

    async def _legacy_info(
        self,
        session: aiohttp.ClientSession,
        url: str,
        is_audio: bool,
    ) -> dict[str, Any] | None:
        headers = {**self.headers, "content-type": "application/json"}
        try:
            async with session.post(
                self.LEGACY_API_URL,
                json={"url": url},
                headers=headers,
            ) as response:
                if response.status != 200:
                    log.warning("Legacy TikTok API HTTP %s", response.status)
                    return None
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            log.warning("Legacy TikTok API error: %s", exc)
            return None

        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not data or not isinstance(data, dict):
            return None

        media_url = self._normalize_media_url(data.get("mp3" if is_audio else "mp4"))
        if not media_url:
            return None

        return {
            "media_url": media_url,
            "title": self._safe_text(data.get("video_info"), "TikTok"),
            "author": self._safe_text(data.get("nick"), "TikTok"),
            "duration": 0,
            "thumbnail": self._normalize_media_url(data.get("video_img")),
        }

    @staticmethod
    def _extension(content_type: str, media_url: str, is_audio: bool) -> str:
        content_type = (content_type or "").split(";", 1)[0].lower()
        by_type = {
            "video/mp4": "mp4",
            "video/webm": "webm",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/mp4": "m4a",
            "audio/x-m4a": "m4a",
            "audio/aac": "aac",
            "audio/webm": "webm",
        }
        if content_type in by_type:
            return by_type[content_type]

        suffix = urlparse(media_url).path.rsplit("/", 1)[-1].rsplit(".", 1)
        if len(suffix) == 2:
            ext = suffix[-1].lower()
            if 1 <= len(ext) <= 5 and ext.isalnum():
                return ext
        return "m4a" if is_audio else "mp4"

    async def _download_media(
        self,
        session: aiohttp.ClientSession,
        info: dict[str, Any],
        is_audio: bool,
    ) -> DownloadedBuffer:
        media_url = info["media_url"]
        request_headers = {
            "user-agent": self.headers["user-agent"],
            "referer": "https://www.tiktok.com/",
        }

        try:
            async with session.get(
                media_url,
                headers=request_headers,
                allow_redirects=True,
            ) as response:
                if response.status != 200:
                    raise DownloadError(f"media HTTP {response.status}")

                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    if int(content_length) > self.MAX_MEDIA_BYTES:
                        raise DownloadTooLarge("TikTok media exceeds upload limit")

                buffer = io.BytesIO()
                async for chunk in response.content.iter_chunked(512 * 1024):
                    buffer.write(chunk)
                    if buffer.tell() > self.MAX_MEDIA_BYTES:
                        raise DownloadTooLarge("TikTok media exceeds upload limit")

                if buffer.tell() == 0:
                    raise DownloadError("empty TikTok media")

                ext = self._extension(
                    response.headers.get("Content-Type", ""),
                    str(response.url),
                    is_audio,
                )
        except DownloadError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise DownloadError(str(exc)) from exc

        buffer.seek(0)
        return DownloadedBuffer(
            buffer=buffer,
            title=info["title"],
            author=info["author"],
            duration=info["duration"],
            ext=ext,
            thumbnail=info.get("thumbnail"),
        )

    async def download(self, url: str, is_audio: bool = False) -> Optional[DownloadedBuffer]:
        normalized_url = self.extract_url(url)
        if not normalized_url:
            log.warning("TikTok URL was not found in message: %r", url)
            return None

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            for provider in (self._tikwm_info, self._legacy_info):
                info = await provider(session, normalized_url, is_audio)
                if (
                    not info
                    and provider == self._tikwm_info
                    and ("vm.tiktok.com" in normalized_url or "vt.tiktok.com" in normalized_url)
                ):
                    await asyncio.sleep(2)
                    info = await provider(session, normalized_url, is_audio)
                if not info:
                    continue
                try:
                    return await self._download_media(session, info, is_audio)
                except DownloadTooLarge:
                    raise
                except DownloadError as exc:
                    log.warning("TikTok media download failed via %s: %s", provider.__name__, exc)

        # Third fallback: yt-dlp. API aggregators occasionally change or rate-limit;
        # keeping a completely different extraction path makes TikTok much more robust.
        try:
            from bot.media_downloader import MediaTooLarge, media_downloader

            media = await media_downloader.download(normalized_url, audio_only=is_audio)
            try:
                size = media.path.stat().st_size
                if size > self.MAX_MEDIA_BYTES:
                    raise DownloadTooLarge("TikTok media exceeds in-memory upload limit")
                payload = await asyncio.to_thread(media.path.read_bytes)
                ext = media.path.suffix.lstrip(".") or ("mp3" if is_audio else "mp4")
                return DownloadedBuffer(
                    buffer=io.BytesIO(payload),
                    title=media.title or "TikTok",
                    author=media.uploader or "TikTok",
                    duration=int(media.duration or 0),
                    ext=ext,
                    thumbnail=media.thumbnail,
                )
            finally:
                media.cleanup()
        except DownloadTooLarge:
            raise
        except MediaTooLarge as exc:
            raise DownloadTooLarge(str(exc)) from exc
        except Exception as exc:
            log.warning("TikTok yt-dlp fallback failed: %s", exc)

        return None
