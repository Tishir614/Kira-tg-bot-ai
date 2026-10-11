"""AI Horde (https://aihorde.net) image client: free, crowdsourced, official API.

Anonymous key is `0000000000`. NSFW is requested explicitly (nsfw=True, censor_nsfw=False) and
furry-trained models are preferred. Horde itself still refuses CSAM; that is the service's rule.
"""
from __future__ import annotations

import asyncio
import os
import time

import aiohttp

from bot.http_client import http_client

API = "https://aihorde.net/api/v2"
CLIENT_AGENT = "KiraBot:2.5:github.com/tishir614/kira-tg-bot-ai"
# Preferred furry models, best first. Matched case-insensitively against live worker models.
DEFAULT_MODELS = "Fluffyrock Unbound,Furry Epoch,yiffy,Pony Diffusion XL,Indigo Furry Mix,Fluffusion"
FURRY_HINTS = ("furry", "fluffy", "yiff", "e621", "pony", "anthro")
# Used only when no furry-trained model has a live worker: general models still draw anthros from tags.
DEFAULT_FALLBACK = "Deliberate,Dreamshaper,Anything Diffusion,stable_diffusion"


class HordeError(RuntimeError):
    pass


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


def build_payload(prompt: str, negative: str, models: list[str], width: int, height: int,
                  steps: int, cfg: float) -> dict:
    is_pony = any("pony" in m.lower() for m in models)
    head = "score_9, score_8_up, score_7_up, " if is_pony else ""
    text = f"{head}{prompt}"[:1500]
    if negative:
        text += f" ### {negative[:600]}"
    return {
        "prompt": text,
        "params": {
            "sampler_name": "k_euler_a", "cfg_scale": cfg, "width": width, "height": height,
            "steps": steps, "n": 1, "karras": True, "post_processing": [],
        },
        "nsfw": True,
        "censor_nsfw": False,
        "trusted_workers": False,
        "slow_workers": True,
        "models": models,
        "r2": True,
        "shared": False,
    }


class AIHorde:
    def __init__(self) -> None:
        self.key = os.getenv("HORDE_API_KEY", "0000000000").strip() or "0000000000"
        self.models = [m for m in os.getenv("HORDE_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
        self.width = self._dim(os.getenv("HORDE_WIDTH", "512"))
        self.height = self._dim(os.getenv("HORDE_HEIGHT", "768"))
        self.steps = max(10, min(50, int(os.getenv("HORDE_STEPS", "28") or 28)))
        self.cfg = max(1.0, min(15.0, float(os.getenv("HORDE_CFG", "7") or 7)))
        self.timeout = max(60, int(os.getenv("HORDE_TIMEOUT", "300") or 300))
        self.fallback = [m for m in os.getenv("HORDE_FALLBACK_MODELS", DEFAULT_FALLBACK).split(",") if m.strip()]
        self.last_models: list[str] = []

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
            text = await resp.text()
            if resp.status >= 400:
                raise HordeError(f"AI Horde HTTP {resp.status}: {text[:300]}")
            try:
                return await resp.json(content_type=None)
            except Exception as exc:
                raise HordeError(f"AI Horde вернул не JSON: {text[:200]}") from exc

    async def generate(self, prompt: str, *, negative: str = "", size: tuple[int, int] | None = None) -> tuple[bytes, str]:
        session = await http_client.get()
        try:
            available = await self._json(session, "GET", "/status/models", params={"type": "image"})
            models = pick_models(available if isinstance(available, list) else [], self.models)
            if not models and self.fallback:
                models = pick_models(available if isinstance(available, list) else [], self.fallback, hints=False)
            if not models:
                raise HordeError("в AI Horde сейчас нет активных фурри-моделей (и запасных тоже)")
            self.last_models = models
            sub = await self._json(session, "POST", "/generate/async",
                                   json=build_payload(prompt, negative, models, *(size or (self.width, self.height)),
                                                      self.steps, self.cfg))
            job = str(sub.get("id") or "") if isinstance(sub, dict) else ""
            if not job:
                raise HordeError(f"AI Horde не принял задачу: {str(sub)[:200]}")
            deadline = time.monotonic() + self.timeout
            while True:
                check = await self._json(session, "GET", f"/generate/check/{job}")
                if check.get("faulted"):
                    raise HordeError("AI Horde: генерация завершилась ошибкой.")
                if check.get("done"):
                    break
                if time.monotonic() > deadline:
                    try:
                        await self._json(session, "DELETE", f"/generate/status/{job}")
                    except Exception:
                        pass
                    raise HordeError("AI Horde: очередь слишком длинная, время вышло.")
                await asyncio.sleep(4)
            status = await self._json(session, "GET", f"/generate/status/{job}")
            gens = status.get("generations") or []
            if not gens:
                raise HordeError("AI Horde не вернул изображение.")
            gen = gens[0]
            if gen.get("censored"):
                raise HordeError("AI Horde пометил результат как цензурный и скрыл его.")
            img = str(gen.get("img") or "")
            if img.startswith("http"):
                async with session.get(img, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status >= 400:
                        raise HordeError(f"AI Horde не отдал файл: HTTP {resp.status}")
                    body = await resp.read()
                    ctype = resp.headers.get("Content-Type", "image/webp")
            else:
                import base64
                body, ctype = base64.b64decode(img), "image/webp"
        except HordeError:
            raise
        except Exception as exc:
            raise HordeError(f"AI Horde недоступен: {exc}") from exc
        if not body or len(body) > 25 * 1024 * 1024:
            raise HordeError("AI Horde вернул пустой или слишком большой файл.")
        return body, ctype


    async def probe(self) -> tuple[bool, str]:
        """Diagnostics: reachability and which models have live workers. Never raises."""
        import time as _t

        started = _t.monotonic()
        try:
            session = await http_client.get()
            available = await self._json(session, "GET", "/status/models", params={"type": "image"})
            available = available if isinstance(available, list) else []
            furry = pick_models(available, self.models)
            general = pick_models(available, self.fallback, hints=False)
            took = _t.monotonic() - started
            if furry:
                return True, f"OK ({took:.1f} c): фурри-модели {', '.join(furry[:3])}"
            if general:
                return True, f"OK ({took:.1f} c), но фурри-моделей нет; запасные: {', '.join(general[:3])}"
            return False, f"доступен, но нет подходящих моделей (активных моделей всего: {len(available)})"
        except Exception as exc:
            return False, f"недоступен: {type(exc).__name__}: {str(exc)[:160]}"


ai_horde = AIHorde()
