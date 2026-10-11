"""Compose e621/booru-style prompts for furry models from translated tags."""
from __future__ import annotations

import re

SPECIES = (
    "fox", "wolf", "dog", "cat", "tiger", "lion", "dragon", "rabbit", "raccoon", "otter", "horse",
    "deer", "bear", "cheetah", "leopard", "panther", "kobold", "lizard", "protogen", "hyena", "skunk",
    "squirrel", "bird", "shark", "bat", "goat", "sheep", "cow", "mouse", "ferret", "jackal", "coyote",
)
_EXPLICIT_RE = re.compile(
    r"(?i)\b(?:nude|naked|sex|penis|pussy|vagina|breasts?|nipples?|cum|anal|oral|blowjob|erection|"
    r"fellatio|masturbat\w*|genitals?|explicit|nsfw|porn|lingerie|topless|bottomless|balls?)\b"
)
_SUGGESTIVE_RE = re.compile(r"(?i)\b(?:bikini|underwear|sexy|sensual|seductive|cleavage|shirtless)\b")
_SOLO_RE = re.compile(r"(?i)\b(?:solo|duo|trio|group|couple|two|three|pair|\d\s*(?:girls?|boys?|people))\b")
_FEMALE_RE = re.compile(r"(?i)\b(?:female|woman|girl|vixen|lady|mare|queen)\b")
_MALE_RE = re.compile(r"(?i)\b(?:male|man|boy|guy|king|stallion)\b")

QUALITY_POSITIVE = (
    "masterpiece, best quality, highres, detailed fur, detailed eyes, detailed background, "
    "soft lighting, sharp focus"
)
QUALITY_NEGATIVE = (
    "worst quality, low quality, lowres, bad anatomy, bad hands, extra digits, missing fingers, "
    "extra limbs, extra tails, extra ears, deformed, disfigured, mutated, blurry, jpeg artifacts, "
    "watermark, signature, text, username, cropped, ugly, human face, human ears, child, young"
)
NSFW_NEGATIVE_EXTRA = "censored, mosaic censoring, bar censor, clothes covering genitalia" 


def rating(tags: str) -> str:
    if _EXPLICIT_RE.search(tags):
        return "rating_explicit"
    if _SUGGESTIVE_RE.search(tags):
        return "rating_questionable"
    return "rating_safe"


def compose(tags: str, *, kira_visual: str = "") -> tuple[str, str]:
    """Return (positive, negative). Never duplicates tags the user already wrote."""
    tags = re.sub(r"\s+", " ", tags or "").strip(" ,")
    low = tags.lower()
    parts: list[str] = []
    if not _SOLO_RE.search(low):
        parts.append("solo")
    if not kira_visual and "anthro" not in low:
        parts.append("anthro" if any(sp in low for sp in SPECIES) else "anthro furry")
    if kira_visual:
        parts.append(kira_visual)
    parts.append(tags)
    parts.append(QUALITY_POSITIVE)
    level = rating(low)
    parts.append(level)
    negative = QUALITY_NEGATIVE
    if level == "rating_explicit":
        negative += ", " + NSFW_NEGATIVE_EXTRA
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk in ", ".join(parts).split(","):
        key = chunk.strip().lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(chunk.strip())
    return ", ".join(ordered), negative
