"""Client for the Perchance "furry-ai" text-to-image generator (https://perchance.org/furry-ai).

Perchance has no public API. This follows the requests the generator page itself makes to
image-generation.perchance.org. That protocol is unofficial and may change, so every step is
configurable through env vars and failures raise PerchanceError so the caller can fall back.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
import uuid

import aiohttp

from bot.http_client import http_client


class PerchanceError(RuntimeError):
    pass


class PerchanceFurry:
    def __init__(self) -> None:
        self.base = os.getenv("PERCHANCE_BASE_URL", "https://image-generation.perchance.org").rstrip("/")
        self.resolution = os.getenv("PERCHANCE_RESOLUTION", "512x768")
        self.guidance = float(os.getenv("PERCHANCE_GUIDANCE", "7") or 7)
        self.channel = os.getenv("PERCHANCE_CHANNEL", "ai-text-to-image-generator")
        self.generator = os.getenv("PERCHANCE_GENERATOR", "furry-ai")
        self.timeout = max(30, int(os.getenv("PERCHANCE_TIMEOUT", "150") or 150))
        self.negative = os.getenv(
            "PERCHANCE_NEGATIVE",
            "worst quality, low quality, bad anatomy, extra limbs, deformed, blurry, watermark, text, signature",
        )
        self._user_key = ""
        self._sem = asyncio.Semaphore(1)

    @property
    def enabled(self) -> bool:
        return os.getenv("PERCHANCE_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}

    async def _get_json(self, session: aiohttp.ClientSession, path: str, params: dict) -> dict:
        async with session.get(
            f"{self.base}{path}", params=params, timeout=aiohttp.ClientTimeout(total=60),
            headers={"Referer": "https://perchance.org/", "Origin": "https://perchance.org"},
        ) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise PerchanceError(f"Perchance HTTP {resp.status}: {body[:200]}")
            try:
                return await resp.json(content_type=None)
            except Exception as exc:
                raise PerchanceError(f"Perchance вернул не JSON: {body[:200]}") from exc

    async def _ensure_key(self, session: aiohttp.ClientSession) -> str:
        if self._user_key:
            return self._user_key
        data = await self._get_json(session, "/api/verifyUser", {
            "thread": "0", "__cacheBust": random.random(),
        })
        key = str(data.get("userKey") or "")
        if not key:
            raise PerchanceError(f"Perchance не выдал userKey: {str(data)[:200]}")
        self._user_key = key
        return key

    async def generate(self, prompt: str, *, negative: str = "", size: tuple[int, int] | None = None) -> tuple[bytes, str]:
        session = await http_client.get()
        async with self._sem:
            try:
                key = await self._ensure_key(session)
                deadline = time.monotonic() + self.timeout
                params = {
                    "prompt": prompt[:2000],
                    "negativePrompt": (negative or self.negative)[:1000],
                    "userKey": key,
                    "__cacheBust": random.random(),
                    "seed": "-1",
                    "resolution": f"{size[0]}x{size[1]}" if size else self.resolution,
                    "guidanceScale": str(self.guidance),
                    "channel": self.channel,
                    "subChannel": "public",
                    "requestId": uuid.uuid4().hex[:12],
                }
                image_id = ""
                while time.monotonic() < deadline:
                    data = await self._get_json(session, "/api/generate", params)
                    status = str(data.get("status") or "")
                    image_id = str(data.get("imageId") or "")
                    if image_id and status in {"success", ""}:
                        break
                    if status in {"invalid_key", "expired_key"}:
                        self._user_key = ""
                        raise PerchanceError("Perchance отклонил ключ, повтори запрос.")
                    if status in {"waiting_for_gpu", "queued", "pending"}:
                        await asyncio.sleep(3)
                        continue
                    raise PerchanceError(f"Perchance статус: {status or data}")
                if not image_id:
                    raise PerchanceError("Perchance не успел сгенерировать изображение.")
                async with session.get(
                    f"{self.base}/api/downloadTemporaryImage", params={"imageId": image_id},
                    timeout=aiohttp.ClientTimeout(total=60),
                    headers={"Referer": "https://perchance.org/"},
                ) as resp:
                    if resp.status >= 400:
                        raise PerchanceError(f"Perchance не отдал картинку: HTTP {resp.status}")
                    body = await resp.read()
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
            except PerchanceError:
                raise
            except Exception as exc:
                raise PerchanceError(f"Perchance недоступен: {exc}") from exc
        if not body or len(body) > 25 * 1024 * 1024:
            raise PerchanceError("Perchance вернул пустой или слишком большой файл.")
        return body, ctype


perchance_furry = PerchanceFurry()
