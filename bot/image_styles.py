"""Style presets for image prompts: `/image лиса стиль:аниме`, `/styles`, random style."""
from __future__ import annotations

import random
import re

STYLES: dict[str, tuple[tuple[str, ...], str]] = {
    "аниме": (("anime", "аниме"), "anime style, cel shading, vibrant colors, detailed eyes"),
    "реализм": (("realistic", "реализм", "фото"), "photorealistic, 85mm photo, natural lighting, sharp focus, detailed fur"),
    "акварель": (("watercolor", "акварель"), "watercolor painting, soft washes, paper texture"),
    "3d": (("3d", "render", "рендер"), "3d render, octane render, subsurface scattering, detailed fur shader"),
    "комикс": (("comic", "комикс"), "indie comic book art style, bold inks, halftone shading"),
    "нуар": (("noir", "нуар", "чб"), "film noir, grainy black and white, dramatic chiaroscuro lighting"),
    "киберпанк": (("cyberpunk", "киберпанк"), "cyberpunk, neon lights, rainy night city, holograms"),
    "фэнтези": (("fantasy", "фэнтези"), "high fantasy illustration, epic lighting, painterly, matte painting"),
    "полароид": (("polaroid", "полароид"), "lost family Polaroid, faded colors, flash photo, found in an attic"),
    "масло": (("oil", "масло"), "oil painting, impasto brush strokes, rich colors, classical portrait"),
    "мультяшный": (("cartoon", "мульт", "мультяшный"), "western cartoon style, clean lineart, flat colors"),
    "пиксель": (("pixel", "пиксель"), "pixel art, 16-bit, limited palette"),
}
_STYLE_RE = re.compile(r"(?i)\b(?:стиль|style)\s*[:=]\s*([\w+\-]+)")


def _resolve(token: str) -> str | None:
    token = token.casefold()
    for name, (aliases, _) in STYLES.items():
        if token == name or token in aliases:
            return name
    return None


def extract_style(prompt: str) -> tuple[str, str | None]:
    """Return (prompt without the style token, style tags or None). `стиль:рандом` picks a random one."""
    match = _STYLE_RE.search(prompt or "")
    if not match:
        return prompt, None
    token = match.group(1).casefold()
    cleaned = (prompt[:match.start()] + prompt[match.end():]).strip(" ,")
    if token in {"рандом", "random", "любой"}:
        return cleaned, STYLES[random.choice(list(STYLES))][1]
    name = _resolve(token)
    return cleaned, STYLES[name][1] if name else None


def styles_help() -> str:
    return "🎨 <b>Стили</b>: " + ", ".join(f"<code>{n}</code>" for n in STYLES) + \
        "\nПример: <code>/image лиса на крыше, стиль:киберпанк</code> или <code>стиль:рандом</code>\n" + formats_help()


# Aspect presets: key -> (width, height). Used by providers that accept explicit sizes.
FORMATS = {
    "portrait": (512, 768), "square": (512, 512), "wide": (768, 512),
}
_FORMAT_ALIASES = {
    "портрет": "portrait", "вертикальный": "portrait", "вертикально": "portrait", "portrait": "portrait",
    "квадрат": "square", "квадратный": "square", "square": "square",
    "широкий": "wide", "пейзаж": "wide", "горизонтальный": "wide", "горизонтально": "wide", "wide": "wide",
}
_FORMAT_RE = re.compile(r"(?i)\b(?:формат|format|размер)\s*[:=]\s*([\w+\-]+)")


def extract_format(prompt: str) -> tuple[str, str | None]:
    """Strip `формат:портрет|квадрат|широкий` from the prompt; return (prompt, key or None)."""
    match = _FORMAT_RE.search(prompt or "")
    if not match:
        return prompt, None
    cleaned = (prompt[:match.start()] + prompt[match.end():]).strip(" ,")
    return cleaned, _FORMAT_ALIASES.get(match.group(1).casefold())


def formats_help() -> str:
    return "Формат: <code>формат:портрет</code> (512×768), <code>формат:квадрат</code> (512×512), <code>формат:широкий</code> (768×512)"
