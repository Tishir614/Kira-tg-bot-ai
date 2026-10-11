"""Deterministic request router: picks a response mode without an extra model call."""
from __future__ import annotations

import re
from dataclasses import dataclass

CHAT, CREATIVE, TECH, ANALYSIS = "chat", "creative", "tech", "analysis"

_TECH_RE = re.compile(
    r"(?i)\b(код|скрипт|функци\w*|баг|traceback|exception|ошибк\w*|docker|python|питон|sql|"
    r"api|json|regex|регуляр\w*|git|линукс|linux|bash|консол\w*|компил\w*|рефактор\w*|"
    r"напиши\s+код|исправь)\b|```|Traceback|\bdef\s+\w+\(|\bimport\s+\w+"
)
_ANALYSIS_RE = re.compile(
    r"(?i)\b(проанализ\w*|анализ\w*|сравн\w*|плюсы\s+и\s+минусы|оцени|рассчита\w*|посчита\w*|"
    r"почему|объясни\s+подробно|разбер\w*|стратеги\w*|вывод\w*|докажи)\b"
)
_CREATIVE_RE = re.compile(
    r"(?i)\b(придумай|сочини|напиши\s+(?:рассказ|стих\w*|историю|песню|сказку|шутку)|"
    r"расскажи\s+(?:историю|сказку|анекдот)|стих\w*|рассказ|сюжет|персонаж\w*|фантази\w*|"
    r"ролев\w*|представь)\b"
)


@dataclass(frozen=True, slots=True)
class Route:
    mode: str
    temperature_delta: float
    complex: bool


_PROFILES = {
    CHAT: (0.0, False),
    CREATIVE: (0.18, False),
    TECH: (-0.28, True),
    ANALYSIS: (-0.22, True),
}


def classify(prompt: str, *, creative: bool = False) -> Route:
    """Return the route for a prompt. Order matters: tech beats analysis beats creative."""
    text = prompt or ""
    if creative:
        mode = CREATIVE
    elif _TECH_RE.search(text):
        mode = TECH
    elif _ANALYSIS_RE.search(text) or len(text) >= 600:
        mode = ANALYSIS
    elif _CREATIVE_RE.search(text):
        mode = CREATIVE
    else:
        mode = CHAT
    delta, is_complex = _PROFILES[mode]
    return Route(mode, delta, is_complex)


def tune_temperature(base: float, route: Route) -> float:
    return round(min(1.3, max(0.05, base + route.temperature_delta)), 3)


_GUIDANCE = {
    TECH: (
        "\nРежим: техническая задача. Сначала молча проверь условия и окружение, затем дай рабочее решение: "
        "код целиком в блоке, команды без выдумок, коротко объясни причину и укажи допущения. Если данных не хватает, "
        "задай один точный вопрос вместо догадок."
    ),
    ANALYSIS: (
        "\nРежим: анализ. Структурируй ответ: короткий вывод, затем аргументы и числа, риски и что проверить. "
        "Различай факты, оценки и предположения; не делай выводов, которых нет в данных."
    ),
    CREATIVE: (
        "\nРежим: творчество. Пиши образно и живо, избегай штампов и пересказа запроса, держи единый стиль и темп."
    ),
    CHAT: (
        "\nРежим: разговор. Отвечай коротко и по-человечески, по сути вопроса; длинные разборы только если просят."
    ),
}
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYR_RE = re.compile(r"[А-Яа-яЁё]")


def guidance(route: Route, prompt: str) -> str:
    """Mode-specific style hint plus language mirroring for clearly non-Russian prompts."""
    text = _GUIDANCE.get(route.mode, "")
    latin, cyr = len(_LATIN_RE.findall(prompt or "")), len(_CYR_RE.findall(prompt or ""))
    if route.mode != TECH and latin >= 12 and cyr == 0:
        text += "\nПользователь пишет не по-русски: отвечай на языке его последнего сообщения."
    return text
