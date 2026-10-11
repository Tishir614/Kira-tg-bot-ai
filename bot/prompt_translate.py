"""Russian -> English image prompt preparation, plus the one hard guard we keep (minors)."""
from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# Sexual/age-ambiguous content involving minors is never generated.
_MINOR_RE = re.compile(
    r"(?i)\b(?:loli\w*|shota\w*|child\w*|kid\b|kids\b|minor\w*|underage|preteen|toddler|baby|"
    r"schoolgirl|schoolboy|teen(?:age|ager)?s?|young\s+(?:girl|boy)|little\s+(?:girl|boy)|cub\s+porn)\b"
    r"|(?:\b(?:лоли\w*|шота\w*|ребён\w*|ребен\w*|дет(?:и|ей|ям|ский|ская|ское)|малолет\w*|несовершеннолет\w*|"
    r"школьниц\w*|школьник\w*|подросток\w*|подростк\w*|девочк\w*|мальчик\w*|малыш\w*|"
    r"детёныш\w*|детеныш\w*)\b)"
)
_AGE_RE = re.compile(r"(?i)\b(?:(\d{1,2})\s*(?:лет|года|год|y\.?o\.?|yo|years?\s*old))\b")

# Fallback glossary used when no LLM is reachable. Furry/booru-style tags.
_GLOSSARY = {
    "лиса": "fox", "лисица": "fox", "лис": "fox", "волк": "wolf", "волчица": "wolf female",
    "кошка": "cat", "кот": "cat", "собака": "dog", "пёс": "dog", "дракон": "dragon",
    "тигр": "tiger", "лев": "lion", "заяц": "rabbit", "кролик": "rabbit", "енот": "raccoon",
    "девушка": "female", "женщина": "woman", "парень": "male", "мужчина": "man",
    "фурри": "anthro furry", "хвост": "tail", "уши": "ears", "лапы": "paws",
    "ночь": "night", "день": "day", "лес": "forest", "город": "city", "пляж": "beach", "пляже": "beach",
    "море": "sea", "дождь": "rain", "снег": "snow", "неон": "neon lights", "замок": "castle",
    "комната": "bedroom", "кровать": "bed", "улыбается": "smiling", "сидит": "sitting",
    "стоит": "standing", "лежит": "lying", "бежит": "running", "спит": "sleeping",
    "красивая": "beautiful", "красивый": "handsome", "большая": "large", "пушистая": "fluffy",
    "чёрная": "black", "черная": "black", "белая": "white", "рыжая": "orange", "красная": "red",
    "синяя": "blue", "зелёная": "green", "зеленая": "green", "фиолетовая": "purple",
    "платье": "dress", "бикини": "bikini", "белье": "lingerie", "бельё": "lingerie",
    "голая": "nude", "обнажённая": "nude", "обнаженная": "nude", "голый": "nude",
    "грудь": "breasts", "киска": "pussy", "член": "penis", "секс": "sex",
    "поцелуй": "kissing", "объятия": "hugging", "вместе": "duo", "двое": "duo",
}
_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")


def has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def is_minor_request(text: str) -> bool:
    """True when the prompt mentions a minor or an age under 18."""
    value = text or ""
    if _MINOR_RE.search(value):
        return True
    return any(int(m.group(1)) < 18 for m in _AGE_RE.finditer(value))


def _lookup(word: str) -> str:
    """Exact match, then a crude stem match so cases like 'пляже'/'лисой' still resolve."""
    if word in _GLOSSARY:
        return _GLOSSARY[word]
    if len(word) >= 4:
        for key, value in _GLOSSARY.items():
            stem = max(3, len(key) - 2)
            if len(key) >= 4 and word[:stem] == key[:stem]:
                return value
    return word if not has_cyrillic(word) else ""


def glossary_translate(text: str) -> str:
    out: list[str] = []
    for word in _WORD_RE.findall((text or "").lower()):
        out.append(_lookup(word))
    return ", ".join(dict.fromkeys(w for w in out if w))


TRANSLATE_INSTRUCTIONS = (
    "You convert image requests (often in Russian) into a single line of English comma-separated "
    "e621/booru-style tags and short phrases for a furry text-to-image model. Keep every detail the "
    "user asked for, including species, body, clothing, pose, setting, mood and explicit content, "
    "exactly as requested and do not censor, soften or add commentary. Output only the tags line."
)


async def to_english_tags(prompt: str, ai_client=None) -> str:
    """Translate a Russian prompt into English tags; never raises."""
    prompt = " ".join((prompt or "").split())
    if not prompt or not has_cyrillic(prompt):
        return prompt
    if ai_client is not None and getattr(ai_client, "enabled", False):
        try:
            text = await ai_client.respond(
                prompt[:1200],
                remember=False,
                instructions=TRANSLATE_INSTRUCTIONS,
                temperature=0.2,
                max_tokens=220,
            )
            text = " ".join(text.replace("\n", ", ").split()).strip(" ,.")
            if text and not has_cyrillic(text):
                return text[:900]
        except Exception:
            pass
    return glossary_translate(prompt) or prompt
