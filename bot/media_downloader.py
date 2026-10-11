from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from bot.config import settings
from bot.internet_tools import InternetDownloader


class MediaDownloadError(RuntimeError):
    pass


class MediaTooLarge(MediaDownloadError):
    pass


@dataclass(slots=True)
class MediaDownload:
    path: Path
    title: str
    webpage_url: str
    duration: int | None
    uploader: str | None
    thumbnail: str | None

    def cleanup(self) -> None:
        try:
            shutil.rmtree(self.path.parent, ignore_errors=True)
        except OSError:
            pass


class _YTDLPLogger:
    def debug(self, msg):
        return None

    def warning(self, msg):
        return None

    def error(self, msg):
        return None


class UniversalMediaDownloader:
    """yt-dlp based public-media downloader.

    No DRM bypassing, no browser-cookie stealing and playlists are disabled by
    default. The feature is meant for public URLs the user is allowed to save.
    """

    def __init__(self) -> None:
        default_limit = "1900" if os.getenv("BOT_API_BASE_URL", "").strip() else "49"
        raw = os.getenv("MEDIA_MAX_DOWNLOAD_MB", os.getenv("INTERNET_MAX_DOWNLOAD_MB", default_limit))
        try:
            mb = int(raw)
        except (TypeError, ValueError):
            mb = 49
        self.max_bytes = max(1, min(mb, 2000)) * 1024 * 1024
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)

    async def download(self, url: str, *, audio_only: bool = False) -> MediaDownload:
        # Initial user-supplied target must be public HTTP(S); this prevents the
        # downloader command from becoming an easy localhost/cloud-metadata probe.
        guard = InternetDownloader()
        normalized = guard._normalize_url(url)
        await guard._validate_public_url(normalized)
        async with self._semaphore:
            return await asyncio.to_thread(self._download_sync, normalized, audio_only)

    def _download_sync(self, url: str, audio_only: bool) -> MediaDownload:
        tmp_dir = Path(tempfile.mkdtemp(prefix="kira_media_"))
        outtmpl = str(tmp_dir / "%(title).120B_%(id)s.%(ext)s")
        opts: dict = {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": _YTDLPLogger(),
            "restrictfilenames": True,
            "max_filesize": self.max_bytes,
            "continuedl": False,
            "retries": 2,
            "fragment_retries": 2,
            "socket_timeout": 30,
            "overwrites": True,
        }

        if audio_only:
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            opts.update({
                "format": "bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best",
                "merge_output_format": "mp4",
            })

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise MediaDownloadError("yt-dlp не вернул информацию о медиа")
        except yt_dlp.utils.DownloadError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            message = str(exc)
            if "larger than max-filesize" in message.lower() or "file is larger" in message.lower():
                raise MediaTooLarge() from exc
            raise MediaDownloadError(message[-900:]) from exc
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

        candidates = [p for p in tmp_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl", ".json"))]
        if not candidates:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise MediaDownloadError("Файл после загрузки не найден")
        path = max(candidates, key=lambda p: p.stat().st_size)
        if path.stat().st_size > self.max_bytes:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise MediaTooLarge()

        return MediaDownload(
            path=path,
            title=str(info.get("title") or path.stem),
            webpage_url=str(info.get("webpage_url") or url),
            duration=int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None,
            uploader=str(info.get("uploader") or info.get("channel") or "") or None,
            thumbnail=str(info.get("thumbnail") or "") or None,
        )

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 15,
            "retries": 1,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": True,
            "logger": _YTDLPLogger(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{max(1, min(limit, 10))}:{query}", download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise MediaDownloadError(str(exc)[-900:]) from exc
        entries = info.get("entries") if isinstance(info, dict) else None
        output: list[dict] = []
        for item in entries or []:
            if not item:
                continue
            output.append({
                "title": item.get("title") or "Без названия",
                "url": item.get("url") if str(item.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={item.get('id')}",
                "duration": item.get("duration"),
                "uploader": item.get("uploader") or item.get("channel"),
            })
        return output


media_downloader = UniversalMediaDownloader()
