from dataclasses import dataclass
import logging
from typing import Any

import aiohttp
import re
from bot.sql import AniListMalCacheManager


log = logging.getLogger(__name__)


@dataclass(slots=True)
class AnimeInfo:
    name: str | None
    video: str | None
    episode: int | None
    episodes: int | None
    description: str | None
    status: str | None = None
    status_raw: str | None = None
    fragment_time: str | None = None
    duration_time: str | None = None
    similarity_percent: str | None = None

# Backward compatibility for older imports.
AnimeData = AnimeInfo


class AnimeAPI:
    def __init__(self, client: Any | None = None):
        self.client = client
        self.trace_url = "https://api.trace.moe"
        self.animelist_url = "https://graphql.anilist.co"
        self.shikimori_endpoint = "https://shikimori.one/api/animes/"
        self.headers = {"Content-Type": "application/json"}
        self._mal_id_cache: dict[int, int] = {}

    @staticmethod
    def prepare_description(description: str | None, template_func, key: str, **kwargs) -> str:
        description = description or ""
        text = re.sub(r"<br.*?>", "\n", description)
        text = re.sub(r"<.*?>", "", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        base_caption = template_func(
            key,
            description="",
            **kwargs
        )

        free_space = 1024 - len(base_caption)

        if free_space <= 0:
            return ""

        if len(text) > free_space:
            text = text[: free_space - 1]

            last_space = text.rfind(" ")
            if last_space != -1:
                text = text[:last_space]

            text += "…"

        return text

    async def check_quota_limit(self) -> str:
        async with aiohttp.ClientSession() as session:
            response = await session.get(url=f"{self.trace_url}/me")
            if response.status == 500:
                return "anime_server_error"
            response_json = await response.json()
            quota = int(response_json.get("quota", 100))
            quota_used = int(response_json.get("quotaUsed", 0))
            if quota > quota_used:
                return ""
            else:
                return "anime_limit"


    def clear_mal_id_cache(self) -> None:
        self._mal_id_cache.clear()

    @staticmethod
    def _format_mm_ss(value: Any) -> str | None:
        try:
            total_seconds = int(float(value))
        except (TypeError, ValueError):
            return None

        if total_seconds < 0:
            return None

        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _build_fragment_time(self, response_data: dict[str, Any]) -> str | None:
        from_time = self._format_mm_ss(response_data.get("from"))
        at_time = self._format_mm_ss(response_data.get("at"))
        to_time = self._format_mm_ss(response_data.get("to"))

        if from_time and to_time and at_time:
            return f"{from_time}-{to_time} ({at_time})"
        if from_time and to_time:
            return f"{from_time}-{to_time}"
        return at_time or from_time or to_time

    @staticmethod
    def _format_release_status(value: Any) -> tuple[str | None, str | None]:
        if not isinstance(value, str):
            return None, None

        raw_status = value.strip().lower()
        if not raw_status:
            return None, None

        ru_status = {
            "anons": "анонс",
            "ongoing": "выходит",
            "released": "вышел",
            "paused": "приостановлен",
            "discontinued": "отменен",
        }.get(raw_status, raw_status)
        return raw_status, ru_status

    @staticmethod
    def _format_similarity(value: Any) -> tuple[float | None, str | None]:
        try:
            similarity = float(value)
        except (TypeError, ValueError):
            return None, None

        if similarity < 0:
            return None, None

        return similarity, f"{similarity * 100:.2f}%"

    async def _get_info(self, session: aiohttp.ClientSession, mal_id: int) -> dict[str, Any] | None:
        response = await session.get(f"{self.shikimori_endpoint}{mal_id}")
        if response.status != 200:
            return None

        data = await response.json()
        if not isinstance(data, dict):
            return None
        return data

    async def _get_mal_id(
        self,
        session: aiohttp.ClientSession,
        animelist_id: int | str | None,
    ) -> int | None:
        if animelist_id is None:
            return None

        try:
            normalized_anilist_id = int(animelist_id)
        except (TypeError, ValueError):
            return None

        if normalized_anilist_id <= 0:
            return None

        cached_mal_id = self._mal_id_cache.get(normalized_anilist_id)
        if cached_mal_id is not None:
            return cached_mal_id

        try:
            persisted_mal_id = await AniListMalCacheManager.get_mal_id(normalized_anilist_id)
        except Exception:
            log.exception("Failed to read mal_id cache from DB for anilist_id=%s", normalized_anilist_id)
            persisted_mal_id = None

        if persisted_mal_id is not None:
            self._mal_id_cache[normalized_anilist_id] = persisted_mal_id
            return persisted_mal_id

        request_payload = {
            "query": "query ($id: Int) { Media(id: $id, type: ANIME) { id idMal } }",
            "variables": {"id": normalized_anilist_id},
        }
        response = await session.post(
            self.animelist_url,
            json=request_payload,
            headers=self.headers,
        )
        if response.status != 200:
            return None

        payload = await response.json()
        media = payload.get("data", {}).get("Media", {})
        mal_id = media.get("idMal")
        if mal_id is None:
            return None

        try:
            parsed_mal_id = int(mal_id)
        except (TypeError, ValueError):
            return None

        self._mal_id_cache[normalized_anilist_id] = parsed_mal_id
        try:
            await AniListMalCacheManager.upsert(normalized_anilist_id, parsed_mal_id)
        except Exception:
            log.exception("Failed to persist mal_id cache for anilist_id=%s", normalized_anilist_id)
        return parsed_mal_id

    async def search(self, file_bytes: bytes) -> AnimeInfo | None:
        endpoint = f"{self.trace_url}/search"
        data = aiohttp.FormData()
        data.add_field(
            "file",
            file_bytes,
            filename="photo.jpg",
            content_type="image/jpeg",
        )

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            response = await session.post(url=endpoint, data=data)
            if response.status != 200:
                return None

            response_json = await response.json()
            result_items = response_json.get("result", [])
            if not result_items:
                return None

            response_data = result_items[0]
            if not isinstance(response_data, dict):
                return None

            anilist_id = response_data.get("anilist")
            mal_id = await self._get_mal_id(session, anilist_id)
            if mal_id is None:
                return None

            info_json = await self._get_info(session, mal_id)
            if info_json is None:
                return None

            _, similarity_percent = self._format_similarity(response_data.get("similarity"))
            status_raw, status = self._format_release_status(info_json.get("status"))

            return AnimeInfo(
                name=info_json.get("russian") or info_json.get("name"),
                video=response_data.get("video"),
                episode=response_data.get("episode"),
                episodes=info_json.get("episodes"),
                description=info_json.get("description_html"),
                status=status,
                status_raw=status_raw,
                fragment_time=self._build_fragment_time(response_data),
                duration_time=self._format_mm_ss(response_data.get("duration")),
                similarity_percent=similarity_percent,
            )
