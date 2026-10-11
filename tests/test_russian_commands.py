from __future__ import annotations

import pathlib
import re

from bot.command_aliases import RUSSIAN_COMMAND_ALIASES, rewrite_command_text, russian_usage


def _registered_commands() -> set[str]:
    commands: set[str] = set()
    root = pathlib.Path(__file__).resolve().parents[1] / "bot"
    for path in root.rglob("*.py"):
        commands.update(re.findall(r'Command\(["\']([^"\']+)["\']\)', path.read_text("utf-8")))
    return commands


def test_every_registered_command_has_unique_russian_alias() -> None:
    registered = _registered_commands()
    assert registered == set(RUSSIAN_COMMAND_ALIASES)
    assert len(set(RUSSIAN_COMMAND_ALIASES.values())) == len(RUSSIAN_COMMAND_ALIASES)


def test_russian_commands_rewrite_without_breaking_legacy() -> None:
    assert rewrite_command_text("/память") == "/memory"
    assert rewrite_command_text("/картинка лиса под дождем") == "/image лиса под дождем"
    assert rewrite_command_text("/память@KiraBot") == "/memory@KiraBot"
    assert rewrite_command_text("/memory") == "/memory"
    assert rewrite_command_text("обычный текст") == "обычный текст"


def test_help_usage_is_localized() -> None:
    assert russian_usage("/image <описание>") == "/картинка <описание>"
    assert russian_usage("/forget_me confirm") == "/забыть_меня confirm"
