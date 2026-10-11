from __future__ import annotations

import asyncio
import os
import random
import re
import time
import uuid
from dataclasses import dataclass

import aiohttp

from bot.http_client import http_client
from bot.horde_client import HordeError, ai_horde
from bot.image_styles import extract_style
from bot.perchance_furry import PerchanceError, perchance_furry
from bot.prompt_translate import is_minor_request, to_english_tags


class ImageGenerationError(RuntimeError):
    pass


class ExplicitImagePrompt(ImageGenerationError):
    """Kept for import compatibility; raised only for prompts involving minors."""


KIRA_VISUAL = (
    "adult anthropomorphic furry fox woman named Kira, clearly 21+, "
    "dark chocolate-black fur, white muzzle and chest, burgundy facial markings, "
    "long wavy dark brown hair with mauve-purple highlights, large black fox ears "
    "with pale inner fur, fluffy dark fox tail with a white tip, elegant gothic purple aesthetic, "
    "expressive eyes, polished digital furry illustration, atmospheric violet lighting"
)

@dataclass(slots=True)
class GeneratedImage:
    data: bytes
    content_type: str
    provider: str


class ImageGenerator:
    """ComfyUI-backed local image generator.

    Kira 1.5 intentionally replaces the old stable-diffusion.cpp wrapper.  The
    bot talks to ComfyUI's stable HTTP API and submits a minimal stock workflow,
    so there are no custom-node dependencies to rot underneath it.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("LOCAL_IMAGE_BASE_URL", "http://comfyui:8188").strip().rstrip("/")
        self.checkpoint = os.getenv("COMFYUI_CHECKPOINT", "DreamShaper_8_pruned.safetensors").strip()
        self.width = self._aligned(os.getenv("LOCAL_IMAGE_WIDTH", "512"))
        self.height = self._aligned(os.getenv("LOCAL_IMAGE_HEIGHT", "512"))
        self.steps = max(4, min(50, int(os.getenv("LOCAL_IMAGE_STEPS", "24") or 24)))
        self.cfg_scale = max(1.0, min(20.0, float(os.getenv("LOCAL_IMAGE_CFG_SCALE", "7.0") or 7.0)))
        self.timeout = aiohttp.ClientTimeout(total=max(120, int(os.getenv("LOCAL_IMAGE_TIMEOUT", "1200") or 1200)), connect=20)
        self._sem = asyncio.Semaphore(max(1, int(os.getenv("LOCAL_IMAGE_CONCURRENCY", "1") or 1)))

    @staticmethod
    def _aligned(value: str) -> int:
        n = max(256, min(1024, int(value or 512)))
        return max(256, (n // 64) * 64)

    async def healthcheck(self) -> str:
        if not self.base_url:
            return "SKIP: local image disabled"
        session = await http_client.get()
        try:
            async with session.get(f"{self.base_url}/system_stats", timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status < 400:
                    return "OK: ComfyUI local"
                return f"ERROR: ComfyUI HTTP {response.status}"
        except Exception as exc:
            return f"ERROR: ComfyUI unavailable: {type(exc).__name__}"

    def _workflow(self, prompt: str, negative: str, seed: int) -> dict:
        return {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": seed, "steps": self.steps, "cfg": self.cfg_scale,
                "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0,
                "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
            }},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": self.width, "height": self.height, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "Kira", "images": ["8", 0]}},
        }

    async def _wait_for_output(self, session: aiohttp.ClientSession, prompt_id: str) -> dict:
        deadline = time.monotonic() + self.timeout.total
        while time.monotonic() < deadline:
            async with session.get(f"{self.base_url}/history/{prompt_id}", timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status >= 400:
                    raise ImageGenerationError(f"ComfyUI history HTTP {response.status}")
                history = await response.json(content_type=None)
            item = history.get(prompt_id) if isinstance(history, dict) else None
            if isinstance(item, dict):
                status = item.get("status") or {}
                if status.get("status_str") == "error":
                    messages = status.get("messages") or []
                    raise ImageGenerationError(f"ComfyUI завершил генерацию с ошибкой: {str(messages)[-800:]}")
                outputs = item.get("outputs") or {}
                for node in outputs.values():
                    images = node.get("images") if isinstance(node, dict) else None
                    if images:
                        return images[0]
            await asyncio.sleep(1.0)
        raise ImageGenerationError("ComfyUI не успел закончить генерацию за отведённое время.")

    async def generate(self, prompt: str, *, kira: bool = False, mature: bool = False) -> GeneratedImage:
        prompt = " ".join((prompt or "").split()).strip()
        if not prompt:
            raise ImageGenerationError("Пустой промпт.")
        if is_minor_request(prompt):
            raise ExplicitImagePrompt("Изображения с несовершеннолетними или персонажами младше 18 я не рисую.")
        prompt, style_tags = extract_style(prompt)
        if not prompt:
            raise ImageGenerationError("Пустой промпт.")
        from bot.ai_client import ai  # local import: ai_client does not depend on images

        english = await to_english_tags(prompt, ai)
        if is_minor_request(english):
            raise ExplicitImagePrompt("Изображения с несовершеннолетними или персонажами младше 18 я не рисую.")
        pieces = [KIRA_VISUAL] if kira else ["adult anthropomorphic furry"]
        pieces.append(english[:1800])
        if style_tags:
            pieces.append(style_tags)
        pieces.append("high quality, detailed, coherent anatomy, detailed face and paws")
        final_prompt = ", ".join(pieces)
        negative = "bad anatomy, extra limbs, extra tails, duplicate face, fused body, deformed paws, blurry, low quality, watermark, text, child, young"

        providers = [x.strip().lower() for x in os.getenv("IMAGE_PROVIDERS", "horde,perchance,comfyui").split(",") if x.strip()]
        errors: list[str] = []
        if "horde" in providers and ai_horde.enabled:
            try:
                data, ctype = await ai_horde.generate(final_prompt, negative=negative)
                return GeneratedImage(data, ctype, "AI Horde (furry)")
            except HordeError as exc:
                errors.append(str(exc))
        if "perchance" in providers and perchance_furry.enabled:
            try:
                data, ctype = await perchance_furry.generate(final_prompt, negative=negative)
                return GeneratedImage(data, ctype, "Perchance furry-ai")
            except PerchanceError as exc:
                errors.append(str(exc))
        if "comfyui" not in providers or not self.base_url:
            raise ImageGenerationError("; ".join(errors) or "Нет доступных генераторов изображений.")
        seed = random.SystemRandom().randint(1, 2**63 - 1)
        client_id = f"kira-{uuid.uuid4()}"
        session = await http_client.get()

        async with self._sem:
            try:
                async with session.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": self._workflow(final_prompt, negative, seed), "client_id": client_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    raw = await response.text()
                    if response.status >= 400:
                        raise ImageGenerationError(f"ComfyUI отклонил workflow (HTTP {response.status}): {raw[:900]}")
                    data = await response.json(content_type=None)
                prompt_id = str(data.get("prompt_id") or "")
                if not prompt_id:
                    raise ImageGenerationError(f"ComfyUI не вернул prompt_id: {raw[:500]}")
                image = await self._wait_for_output(session, prompt_id)
                params = {"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
                async with session.get(f"{self.base_url}/view", params=params, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status >= 400:
                        raise ImageGenerationError(f"ComfyUI не отдал результат: HTTP {response.status}")
                    body = await response.read()
                    ctype = response.headers.get("Content-Type", "image/png")
            except ImageGenerationError:
                raise
            except Exception as exc:
                raise ImageGenerationError(
                    "ComfyUI недоступен. Запусти: docker compose --profile image up -d --build comfyui. Ошибка: " + str(exc)
                ) from exc

        if not body or len(body) > 25 * 1024 * 1024:
            raise ImageGenerationError("ComfyUI вернул пустой или слишком большой файл.")
        return GeneratedImage(body, ctype, f"ComfyUI/{self.checkpoint} (local)")


image_generator = ImageGenerator()
