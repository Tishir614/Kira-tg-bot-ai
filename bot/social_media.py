from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from bot.internet_tools import InternetDownloader, InternetSearch
from bot.media_downloader import MediaDownloadError, media_downloader


@dataclass(slots=True)
class SocialMediaInfo:
    platform: str
    title: str
    url: str
    uploader: str | None = None
    duration: int | None = None
    is_live: bool = False
    view_count: int | None = None
    like_count: int | None = None
    thumbnail: str | None = None


class SocialMediaError(RuntimeError):
    pass


class _QuietLogger:
    def debug(self, _msg):
        return None
    def warning(self, _msg):
        return None
    def error(self, _msg):
        return None


def detect_platform(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").casefold()
    except ValueError:
        return "web"
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        return "youtube"
    if host.endswith("tiktok.com"):
        return "tiktok"
    if host.endswith("twitch.tv"):
        return "twitch"
    return "web"


class SocialMediaService:
    """Public social-media integration without account-cookie theft.

    YouTube/TikTok/Twitch URLs are inspected with yt-dlp. Search uses YouTube's
    ytsearch extractor or the existing metasearch layer for public TikTok/Twitch
    links. Private/DRM media is intentionally not bypassed.
    """

    _TWITCH_NAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")

    async def inspect(self, url: str) -> SocialMediaInfo:
        guard = InternetDownloader()
        normalized = guard._normalize_url(url)
        await guard._validate_public_url(normalized)
        return await asyncio.to_thread(self._inspect_sync, normalized)

    def _inspect_sync(self, url: str) -> SocialMediaInfo:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 1,
            "logger": _QuietLogger(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise SocialMediaError(str(exc)[-900:]) from exc
        if not isinstance(info, dict):
            raise SocialMediaError("источник не вернул метаданные")
        if info.get("entries"):
            first = next((x for x in info.get("entries") or [] if isinstance(x, dict)), None)
            if first:
                info = first
        live_status = str(info.get("live_status") or "").lower()
        is_live = bool(info.get("is_live")) or live_status in {"is_live", "is_upcoming"}
        duration = info.get("duration")
        return SocialMediaInfo(
            platform=detect_platform(str(info.get("webpage_url") or url)),
            title=str(info.get("title") or info.get("fulltitle") or "Без названия")[:500],
            url=str(info.get("webpage_url") or info.get("original_url") or url),
            uploader=str(info.get("uploader") or info.get("channel") or "")[:180] or None,
            duration=int(duration) if isinstance(duration, (int, float)) else None,
            is_live=is_live,
            view_count=int(info["view_count"]) if isinstance(info.get("view_count"), (int, float)) else None,
            like_count=int(info["like_count"]) if isinstance(info.get("like_count"), (int, float)) else None,
            thumbnail=str(info.get("thumbnail") or "") or None,
        )

    async def search(self, platform: str, query: str, limit: int = 5) -> list[dict]:
        platform = platform.casefold().strip()
        query = " ".join((query or "").split()).strip()
        limit = max(1, min(int(limit), 8))
        if not query:
            return []
        if platform == "youtube":
            rows = await media_downloader.search(query, limit=limit)
            return [{**row, "platform": "youtube"} for row in rows]

        domain = {"tiktok": "tiktok.com", "twitch": "twitch.tv"}.get(platform)
        if not domain:
            return []
        searcher = InternetSearch()
        results = await searcher.search(f"site:{domain} {query}", max_results=limit * 2)
        output: list[dict] = []
        seen: set[str] = set()
        for item in results:
            url = item.url
            if domain not in (urlparse(url).hostname or "").casefold():
                continue
            if url in seen:
                continue
            seen.add(url)
            output.append({
                "title": item.title or query,
                "url": url,
                "uploader": None,
                "duration": None,
                "platform": platform,
            })
            if len(output) >= limit:
                break
        return output

    async def twitch_channel(self, value: str) -> SocialMediaInfo:
        value = (value or "").strip()
        if self._TWITCH_NAME.fullmatch(value):
            value = f"https://www.twitch.tv/{value}"
        return await self.inspect(value)

    async def download(self, url: str, *, audio_only: bool = False):
        # Inspect first so live streams do not create an effectively unbounded download.
        info = await self.inspect(url)
        if info.platform == "twitch" and info.is_live:
            raise SocialMediaError("live_now")
        return await media_downloader.download(url, audio_only=audio_only)


social_media = SocialMediaService()
