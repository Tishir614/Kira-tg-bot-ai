"""Inline buttons under generated images: 'another variant' and 'random style'."""
from __future__ import annotations

import secrets
from collections import OrderedDict
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.image_styles import _STYLE_RE


@dataclass(slots=True)
class ImageRequest:
    user_id: int
    prompt: str
    kira: bool


_store: "OrderedDict[str, ImageRequest]" = OrderedDict()
_MAX = 300


def remember(user_id: int, prompt: str, kira: bool) -> str:
    token = secrets.token_urlsafe(6)
    _store[token] = ImageRequest(user_id, prompt, kira)
    while len(_store) > _MAX:
        _store.popitem(last=False)
    return token


def lookup(token: str) -> ImageRequest | None:
    return _store.get(token)


def strip_style(prompt: str) -> str:
    return _STYLE_RE.sub("", prompt).strip(" ,")


def keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"img:again:{token}"),
        InlineKeyboardButton(text="🎨 Другой стиль", callback_data=f"img:style:{token}"),
    ]])
