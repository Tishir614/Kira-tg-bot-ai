from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    title: str
    reason: str
    action: str = "warn"  # warn | reminder | review
    priority: int = 50


_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.|t\.me/|telegram\.me/)\S+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s()\-]{8,}\d)(?!\d)")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

_STRONG_INSULT_RE = re.compile(
    r"(?i)(?:\b(?:идиот|дебил|дегенерат|мразь|ублюдок|тварь|чмо)\b|"
    r"\bзаткнись\b|\bсдохни\b|\bпош[её]л\s+нах\w*)"
)
_IDENTITY_CUE_RE = re.compile(
    r"(?i)\b(?:раса|национальност\w*|религи\w*|вера|верующ\w*|пол\w*\s+взгляд\w*|интерес\w*)\b"
)
_RELIGION_HOSTILITY_RE = re.compile(
    r"(?i)(?:\b(?:религи\w*|вера|верующ\w*)\b.{0,40}\b(?:мерзк\w*|туп\w*|идиот\w*|говн\w*)\b|"
    r"\b(?:мерзк\w*|туп\w*|идиот\w*|говн\w*)\b.{0,40}\b(?:религи\w*|вера|верующ\w*)\b)"
)
_POLITICS_STRONG_RE = re.compile(
    r"(?i)\b(?:политик\w*|агитаци\w*|выбор(?:ы|ах|ов|ами)|президент\w*|депутат\w*|санкци\w*|геополит\w*|"
    r"нато|политическ\w*\s+(?:партия|спор|митинг|лозунг)|война\s+между\s+\w+)\b"
)
_HISTORY_RE = re.compile(r"(?i)\b(?:истори\w*|историческ\w*|архив\w*|\d{3,4}\s*год\w*)\b")
_DONOX_CUE_RE = re.compile(
    r"(?i)\b(?:адрес|телефон|номер|паспорт|почта|email|e-mail|айпи|ip|личн\w*\s+данн\w*|вот\s+его|вот\s+ее|вот\s+её)\b"
)
_AD_PROMO_RE = re.compile(
    r"(?i)\b(?:реклам\w*|подписывай\w*|вступай\w*|мой\s+канал|наш\s+канал|промокод\w*|скидк\w*|розыгрыш\w*)\b"
)
_IRL_ADULT_RE = re.compile(
    r"(?i)\b(?:порно|porn|xxx|эротик\w*)\b.*\b(?:irl|реальн\w*\s+(?:люд\w*|мужчин\w*|женщин\w*|девуш\w*|парн\w*))\b|"
    r"\b(?:irl|реальн\w*\s+(?:люд\w*|мужчин\w*|женщин\w*|девуш\w*|парн\w*))\b.*\b(?:порно|porn|xxx|эротик\w*)\b"
)
_FURRY_ADULT_RE = re.compile(r"(?i)\b(?:фурри|furry|йифф|yiff|фурсьют|fursuit)\b")
_RULE_DISCUSSION_RE = re.compile(r"(?i)\b(?:правил\w*|запрещен\w*|разрешен\w*|модераци\w*)\b")
_RP_MARKER_RE = re.compile(r"(?:\*[^*]{20,}\*|^\s*(?:rp|рп)\s*[:：]|\([^\n]{30,}\))", re.I | re.M)


def _compact(text: str) -> str:
    return " ".join((text or "").replace("\u200b", " ").split())


def inspect_text(
    text: str,
    *,
    has_media: bool = False,
    forwarded_from_channel: bool = False,
) -> list[RuleHit]:
    """High-confidence rule checks only.

    The engine intentionally does not try to infer intent, protected traits or consent
    from vague phrases. Ambiguous cases are left to human moderation/reporting.
    """
    value = _compact(text)
    if not value:
        if forwarded_from_channel:
            return [RuleHit("2.3", "Реклама/пересылка", "Пересылка из канала/группы без очистки источника.", priority=90)]
        return []

    hits: list[RuleHit] = []
    rule_discussion = bool(_RULE_DISCUSSION_RE.search(value))

    if _STRONG_INSULT_RE.search(value):
        hits.append(RuleHit("1", "Уважение и конфликты", "Оскорбление, агрессивная реплика или провокация.", priority=100))

    if _IDENTITY_CUE_RE.search(value) and _STRONG_INSULT_RE.search(value):
        hits.append(RuleHit("1.3", "Дискриминация", "Оскорбление участника по признакам или интересам.", priority=105))

    if _RELIGION_HOSTILITY_RE.search(value):
        hits.append(RuleHit("1.4", "Уважение веры", "Оскорбление религии или веры.", priority=105))

    if not rule_discussion and not _HISTORY_RE.search(value) and _POLITICS_STRONG_RE.search(value):
        hits.append(RuleHit("1.1", "Политика", "Политическая тема/агитация вне разрешённого исторического контекста.", priority=85))

    if _DONOX_CUE_RE.search(value) and (_PHONE_RE.search(value) or _EMAIL_RE.search(value) or _IP_RE.search(value)):
        hits.append(RuleHit("1.2", "Личная информация", "Публикация потенциально личных данных участника.", priority=120))

    url = bool(_URL_RE.search(value))
    if forwarded_from_channel or (url and _AD_PROMO_RE.search(value)) or re.search(r"(?i)\bt\.me/", value):
        hits.append(RuleHit("2.3", "Реклама/пересылка", "Реклама, приглашение или ссылка на сторонний канал/группу.", priority=95))

    if has_media and not rule_discussion and _IRL_ADULT_RE.search(value) and not _FURRY_ADULT_RE.search(value):
        hits.append(RuleHit("2.2", "IRL 18+", "Подпись указывает на 18+ контент с реальными людьми.", priority=115))

    if len(value) >= 3000 and _RP_MARKER_RE.search(value):
        hits.append(RuleHit("3.3", "Длинный RP", "Очень длинный RP-пост может мешать общению в общем чате.", priority=70))

    # Stable order and no duplicate rule ids.
    seen: set[str] = set()
    result: list[RuleHit] = []
    for hit in sorted(hits, key=lambda x: x.priority, reverse=True):
        if hit.rule_id in seen:
            continue
        seen.add(hit.rule_id)
        result.append(hit)
    return result
