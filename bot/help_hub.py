"""Interactive help: ONE message that is edited in place via category buttons."""
from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.command_aliases import russian_usage
from bot.help_ui import ADMIN_SECTIONS, PUBLIC_SECTIONS

PAGE_LIMIT = 3500
LINE = "━━━━━━━━━━━━━━━━"


def categories(admin: bool, legacy: Mapping[str, Any] | None = None) -> list[tuple[str, list[str]]]:
    """[(title, [formatted command lines])] — public first, then text commands, then admin."""
    out: list[tuple[str, list[str]]] = []

    def fmt(command: str, description: str) -> str:
        return f"▫️ <code>{html.escape(russian_usage(command))}</code>\n    <i>{html.escape(description)}</i>"

    for title, commands in PUBLIC_SECTIONS:
        out.append((title, [fmt(c, d) for c, d in commands]))
    if legacy:
        public = [(n, c) for n, c in legacy.items() if not getattr(c, "admin_only", False)]
        if public:
            out.append(("⌨️ Текстовые команды", [fmt(str(n), str(getattr(c, "description", ""))) for n, c in public]))
    if admin:
        for title, commands in ADMIN_SECTIONS:
            out.append((title, [fmt(c, d) for c, d in commands]))
        if legacy:
            adm = [(n, c) for n, c in legacy.items() if getattr(c, "admin_only", False)]
            if adm:
                out.append(("🔧 Текстовые команды админов", [fmt(str(n), str(getattr(c, "description", ""))) for n, c in adm]))
    return out


def paginate(lines: list[str], limit: int = PAGE_LIMIT) -> list[list[str]]:
    pages: list[list[str]] = [[]]
    size = 0
    for line in lines:
        if pages[-1] and size + len(line) + 1 > limit:
            pages.append([])
            size = 0
        pages[-1].append(line)
        size += len(line) + 1
    return pages


def render_main(cats: list[tuple[str, list[str]]]) -> str:
    total = sum(len(lines) for _, lines in cats)
    rows = "\n".join(f"{title} — <b>{len(lines)}</b>" for title, lines in cats)
    return (
        "🦊 <b>Kira • Центр помощи</b>\n"
        f"{LINE}\n"
        "<blockquote>Выбери раздел кнопкой ниже — сообщение само превратится в список команд "
        "с объяснением каждой. Русские и английские названия работают одинаково.</blockquote>\n"
        f"{rows}\n"
        f"{LINE}\n"
        f"📚 Всего команд: <b>{total}</b>\n"
        "💡 Можно просто писать Кире: <code>Кира, расскажи про…</code> или в личке без команды."
    )


def render_category(cats: list[tuple[str, list[str]]], idx: int, page: int) -> tuple[str, int]:
    title, lines = cats[idx]
    pages = paginate(lines)
    page = max(0, min(page, len(pages) - 1))
    tail = f" · стр. {page + 1}/{len(pages)}" if len(pages) > 1 else ""
    text = f"<b>{title}</b>{tail}\n{LINE}\n" + "\n".join(pages[page])
    return text, len(pages)


def _short(title: str) -> str:
    return title if len(title) <= 24 else title[:23] + "…"


def keyboard(cats: list[tuple[str, list[str]]], scope: str, *, idx: int | None = None, page: int = 0,
             pages: int = 1, support_url: str = "", site_url: str = "") -> InlineKeyboardMarkup:
    """scope: 'u' (public only) or 'a' (admin sections too); encoded into callback data."""
    rows: list[list[InlineKeyboardButton]] = []
    if idx is None:
        row: list[InlineKeyboardButton] = []
        for i, (title, _) in enumerate(cats):
            row.append(InlineKeyboardButton(text=_short(title), callback_data=f"hub:{scope}:c:{i}:0"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    else:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"hub:{scope}:c:{idx}:{page - 1}"))
        nav.append(InlineKeyboardButton(text="🏠 Меню", callback_data=f"hub:{scope}:m:0:0"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"hub:{scope}:c:{idx}:{page + 1}"))
        rows.append(nav)
        neighbours = []
        if idx > 0:
            neighbours.append(InlineKeyboardButton(text="⬅️ Раздел", callback_data=f"hub:{scope}:c:{idx - 1}:0"))
        if idx < len(cats) - 1:
            neighbours.append(InlineKeyboardButton(text="Раздел ➡️", callback_data=f"hub:{scope}:c:{idx + 1}:0"))
        if neighbours:
            rows.append(neighbours)
    extra: list[InlineKeyboardButton] = []
    if site_url:
        extra.append(InlineKeyboardButton(text="🌐 Сайт", url=site_url))
    if support_url:
        extra.append(InlineKeyboardButton(text="🛟 Поддержка", url=support_url))
    if extra:
        rows.append(extra)
    return InlineKeyboardMarkup(inline_keyboard=rows)
