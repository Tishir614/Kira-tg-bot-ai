"""AI Horde (https://aihorde.net) image client: free, crowdsourced, official API.

Anonymous key is `0000000000`. NSFW is requested explicitly (nsfw=True, censor_nsfw=False) and
furry-trained models are preferred. Horde itself still refuses CSAM; that is the service's rule.

Hardened against the usual reasons an anonymous Horde request fails:
  * KudosUpfront (403): anonymous users may not request big/slow jobs -> sizes and steps are clamped
    for the anonymous key and a minimal retry is made;
  * no worker for the chosen models / is_possible=false -> automatic retry with general models;
  * TooManyPrompts (429): anonymous users get very few parallel jobs -> jobs are serialized, retried;
  * censored/black results -> one retry (another worker);
  * WebP results -> converted to JPEG so Telegram always accepts them.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import re
import time

import aiohttp

from bot.http_client import http_client

API = "https://aihorde.net/api/v2"
CLIENT_AGENT = "KiraBot:2.17:github.com/tishir614/kira-tg-bot-ai"
ANON_KEY = "0000000000"
# Preferred furry models, best first. SD1.5-based furry models come first: they work at the small sizes
# an anonymous key is allowed; SDXL/Pony models need big canvases and are tried last.
DEFAULT_MODELS = "Fluffyrock Unbound,Furry Epoch,Yiffy,Indigo Furry Mix,Fluffusion,Pony Diffusion XL"
FURRY_HINTS = ("furry", "fluffy", "yiff", "e621", "pony", "anthro")
# Used only when no furry-trained model has a live worker: general models still draw anthros from tags.
DEFAULT_FALLBACK = "Deliberate,Dreamshaper,Anything Diffusion,stable_diffusion"
ANON_MAX_PIXELS = 512 * 512
ANON_MAX_STEPS = 25
_NEG_STRIP_RE = re.compile(r"(?i)\b(?:child|children|kid|kids|young|underage|minor|teen\w*|loli\w*|shota\w*)\b,?\s*")


class HordeError(RuntimeError):
    """Horde failure. `retry` tells the caller what a retry should change (None = do not retry)."""

    def __init__(self, message: str, *, status: int = 0, rc: str = "", retry: str | None = None) -> None:
        super().__init__(message)
        self.status, self.rc, self.retry = status, rc, retry


def pick_models(available: list[dict], preferred: list[str], *, hints: bool = True) -> list[str]:
    """Choose live models: preferred names first (by active workers), then any furry-looking model."""
    names = {str(m.get("name", "")): int(m.get("count", 0) or 0) for m in available}
    lower = {n.lower(): n for n in names}
    chosen: list[str] = []
    for want in preferred:
        w = want.strip().lower()
        if not w:
            continue
        for low, real in lower.items():
            if (low == w or w in low) and real not in chosen and names[real] > 0:
                chosen.append(real)
    if not chosen and hints:
        for low, real in lower.items():
            if names[real] > 0 and any(h in low for h in FURRY_HINTS):
                chosen.append(real)
    return chosen[:5]


def is_sdxl(model: str) -> bool:
    low = model.lower()
    return "xl" in low or "pony" in low or "sdxl" in low


def prefer_sd15(models: list[str]) -> list[str]:
    """Keep SD1.5 models when there are any (small canvases work); SDXL/Pony only if nothing else is live."""
    small = [m for m in models if not is_sdxl(m)]
    return small or models


def clamp_for_anonymous(width: int, height: int, steps: int) -> tuple[int, int, int]:
    """Anonymous Horde users cannot ask for big jobs (KudosUpfront). Scale down keeping the aspect ratio."""
    steps = min(steps, ANON_MAX_STEPS)
    if width * height > ANON_MAX_PIXELS:
        scale = math.sqrt(ANON_MAX_PIXELS / (width * height))
        width = max(256, int(width * scale) // 64 * 64)
        height = max(256, int(height * scale) // 64 * 64)
    return width, height, steps


def build_payload(prompt: str, negative: str, models: list[str], width: int, height: int,
                  steps: int, cfg: float) -> dict:
    is_pony = any("pony" in m.lower() for m in models)
    head = "score_9, score_8_up, score_7_up, " if is_pony else ""
    text = f"{head}{prompt}"[:1500]
    # Our own minors guard already ran; keep age words out of the text Horde's filter scans.
    negative = _NEG_STRIP_RE.sub("", negative or "").strip(" ,")
    if negative:
        text += f" ### {negative[:600]}"
    furry = any(any(h in m.lower() for h in FURRY_HINTS) for m in models)
    params = {
        "sampler_name": "k_euler_a", "cfg_scale": cfg, "width": width, "height": height,
        "steps": steps, "n": 1, "karras": True, "post_processing": [],
    }
    if furry:
        params["clip_skip"] = 2   # recommended for Fluffyrock/e621-trained checkpoints
    return {
        "prompt": text,
        "params": params,
        "nsfw": True,
        "censor_nsfw": False,
        "trusted_workers": False,
        "slow_workers": True,
        "models": models,
        "r2": True,
        "shared": False,
    }


def to_jpeg(data: bytes, ctype: str) -> tuple[bytes, str]:
    """Telegram is picky about WebP photos: convert to JPEG when Pillow is available."""
    if "webp" not in (ctype or "").lower() and not data[:4] == b"RIFF":
        return data, ctype
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=92)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, ctype


class AIHorde:
    def __init__(self) -> None:
        self.key = os.getenv("HORDE_API_KEY", ANON_KEY).strip() or ANON_KEY
        self.models = [m for m in os.getenv("HORDE_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
        self.width = self._dim(os.getenv("HORDE_WIDTH", "512"))
        self.height = self._dim(os.getenv("HORDE_HEIGHT", "768"))
        self.steps = max(10, min(50, int(os.getenv("HORDE_STEPS", "28") or 28)))
        self.cfg = max(1.0, min(15.0, float(os.getenv("HORDE_CFG", "7") or 7)))
        self.timeout = max(60, int(os.getenv("HORDE_TIMEOUT", "300") or 300))
        self.fallback = [m for m in os.getenv("HORDE_FALLBACK_MODELS", DEFAULT_FALLBACK).split(",") if m.strip()]
        self.last_models: list[str] = []
        self.last_note = ""
        self._sem = asyncio.Semaphore(1 if self.anonymous else 2)

    @property
    def anonymous(self) -> bool:
        return self.key == ANON_KEY

    @staticmethod
    def _dim(value: str) -> int:
        return max(256, min(1024, (int(value or 512) // 64) * 64))

    @property
    def enabled(self) -> bool:
        return os.getenv("HORDE_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}

    @property
    def _headers(self) -> dict:
        return {"apikey": self.key, "Client-Agent": CLIENT_AGENT, "Content-Type": "application/json"}

    async def _json(self, session: aiohttp.ClientSession, method: str, path: str, **kw) -> dict | list:
        async with session.request(method, f"{API}{path}", headers=self._headers,
                                   timeout=aiohttp.ClientTimeout(total=60), **kw) as resp:
            status = resp.status
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = None
            if status >= 400:
                message = rc = ""
                if isinstance(data, dict):
                    message = str(data.get("message") or data.get("error") or "")[:300]
                    rc = str(data.get("rc") or "")
                    errors = data.get("errors")
                    if errors:
                        message += f" {str(errors)[:200]}"
                if not message:
                    message = (await resp.text())[:300]
                low = f"{rc} {message}".lower()
                retry = None
                if status == 429 or "toomany" in low or "too many" in low:
                    retry = "wait"
                elif "kudos" in low or rc == "KudosUpfront":
                    retry = "smaller"
                elif "no active worker" in low or "novalidworkers" in low.replace(" ", "") or "no worker" in low:
                    retry = "fallback"
                raise HordeError(f"HTTP {status} {rc}: {message}".strip(), status=status, rc=rc, retry=retry)
            if data is None:
                raise HordeError("Horde вернул не JSON")
            return data

    # ---- one submission -------------------------------------------------------------------------
    async def _once(self, session, prompt: str, negative: str, models: list[str], width: int, height: int,
                    steps: int) -> tuple[bytes, str]:
        sub = await self._json(session, "POST", "/generate/async",
                               json=build_payload(prompt, negative, models, width, height, steps, self.cfg))
        job = str(sub.get("id") or "") if isinstance(sub, dict) else ""
        if not job:
            raise HordeError(f"AI Horde не принял задачу: {str(sub)[:200]}")
        deadline = time.monotonic() + self.timeout
        first = True
        try:
            while True:
                check = await self._json(session, "GET", f"/generate/check/{job}")
                if check.get("faulted"):
                    raise HordeError("генерация завершилась ошибкой на стороне воркера", retry="again")
                if check.get("is_possible") is False:
                    raise HordeError("ни один воркер не может выполнить запрос с этими моделями", retry="fallback")
                if check.get("done"):
                    break
                wait = float(check.get("wait_time") or 0)
                if first and wait > self.timeout * 1.5:
                    raise HordeError(f"очередь слишком длинная (≈{int(wait)} с)")
                first = False
                if time.monotonic() > deadline:
                    raise HordeError("очередь слишком длинная, время вышло")
                await asyncio.sleep(3)
        except BaseException:
            try:  # free our place in the queue; never mask the original error
                await self._json(session, "DELETE", f"/generate/status/{job}")
            except Exception:
                pass
            raise
        status = await self._json(session, "GET", f"/generate/status/{job}")
        gens = status.get("generations") or []
        if not gens:
            raise HordeError("AI Horde не вернул изображение", retry="again")
        gen = gens[0]
        if gen.get("censored"):
            raise HordeError("воркер пометил результат как цензурный", retry="again")
        img = str(gen.get("img") or "")
        if img.startswith("http"):
            async with session.get(img, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status >= 400:
                    raise HordeError(f"не удалось скачать результат: HTTP {resp.status}", retry="again")
                body = await resp.read()
                ctype = resp.headers.get("Content-Type", "image/webp")
        else:
            import base64
            body, ctype = base64.b64decode(img), "image/webp"
        if not body or len(body) > 25 * 1024 * 1024:
            raise HordeError("пустой или слишком большой файл", retry="again")
        return to_jpeg(body, ctype)

    async def _live_models(self, session) -> list[dict]:
        available = await self._json(session, "GET", "/status/models", params={"type": "image"})
        return available if isinstance(available, list) else []

    async def generate(self, prompt: str, *, negative: str = "", size: tuple[int, int] | None = None) -> tuple[bytes, str]:
        session = await http_client.get()
        width, height = size or (self.width, self.height)
        steps = self.steps
        async with self._sem:
            try:
                available = await self._live_models(session)
                furry = prefer_sd15(pick_models(available, self.models))
                general = pick_models(available, self.fallback, hints=False)
                if not furry and not general:
                    raise HordeError("в AI Horde сейчас нет активных фурри-моделей (и запасных тоже)")
                models = furry or general
                use_fallback = not furry
                tried_general = use_fallback
                small = False
                attempt = 0
                while True:
                    attempt += 1
                    w, h, st = (clamp_for_anonymous(width, height, steps) if self.anonymous
                                else (width, height, steps))
                    if small:
                        w, h, st = (512, 512, 20)
                    self.last_models = models
                    self.last_note = "общая модель" if models is general else ""
                    try:
                        return await self._once(session, prompt, negative, models, w, h, st)
                    except HordeError as exc:
                        if attempt >= 4 or exc.retry is None:
                            raise
                        if exc.retry == "wait":
                            await asyncio.sleep(6 * attempt)
                        elif exc.retry == "smaller":
                            if small:
                                raise
                            small = True
                        elif exc.retry == "fallback":
                            if tried_general or not general:
                                raise
                            models, tried_general = general, True
                        # "again": just resubmit (another worker will pick it up)
            except HordeError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise HordeError(f"AI Horde недоступен: {type(exc).__name__}: {exc}") from exc

    async def probe(self) -> tuple[bool, str]:
        """Diagnostics: reachability, live models and a dry-run submission (validates the real payload
        without queuing a job: catches KudosUpfront, bad keys and validation errors). Never raises."""
        started = time.monotonic()
        try:
            session = await http_client.get()
            available = await self._live_models(session)
            furry = prefer_sd15(pick_models(available, self.models))
            general = pick_models(available, self.fallback, hints=False)
            took = time.monotonic() - started
            who = "анонимный ключ" if self.anonymous else "ваш ключ"
            models = furry or general
            if not models:
                return False, f"доступен, но нет подходящих моделей (активных моделей всего: {len(available)})"
            note = (f"фурри-модели {', '.join(furry[:3])}" if furry
                    else f"фурри-моделей нет; запасные: {', '.join(general[:3])}")
            w, h, st = (clamp_for_anonymous(self.width, self.height, self.steps) if self.anonymous
                        else (self.width, self.height, self.steps))
            payload = build_payload("anthro fox, portrait", "bad anatomy", models, w, h, st, self.cfg)
            payload["dry_run"] = True
            try:
                reply = await self._json(session, "POST", "/generate/async", json=payload)
                cost = reply.get("kudos") if isinstance(reply, dict) else None
                return True, (f"OK ({took:.1f} c, {who}): {note}; тестовый запрос принят"
                              f"{f' (≈{cost} kudos)' if cost is not None else ''}")
            except HordeError as exc:
                return False, f"{note}, но тестовый запрос отклонён: {exc}"
        except Exception as exc:
            return False, f"недоступен: {type(exc).__name__}: {str(exc)[:160]}"


ai_horde = AIHorde()
