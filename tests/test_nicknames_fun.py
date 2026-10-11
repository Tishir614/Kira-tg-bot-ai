from __future__ import annotations

from pathlib import Path

from bot.command_aliases import rewrite_command_text

ROOT = Path(__file__).resolve().parents[1]


def test_nickname_commands_are_russian_aliases() -> None:
    assert rewrite_command_text('/ник Лис') == '/nick Лис'
    assert rewrite_command_text('/мой_ник') == '/my_nick'
    assert rewrite_command_text('/удалить_ник глобально') == '/remove_nick глобально'


def test_fun_commands_are_russian_aliases() -> None:
    assert rewrite_command_text('/правда') == '/truth'
    assert rewrite_command_text('/действие') == '/dare'
    assert rewrite_command_text('/оракул') == '/oracle'
    assert rewrite_command_text('/дуэль') == '/duel'
    assert rewrite_command_text('/комплимент') == '/compliment'


def test_nickname_is_wired_into_ai_rp_and_forget_me() -> None:
    ai = (ROOT / 'bot' / 'ai_client.py').read_text('utf-8')
    rp = (ROOT / 'bot' / 'handlers' / 'chat_updates.py').read_text('utf-8')
    memory = (ROOT / 'bot' / 'kira_next.py').read_text('utf-8')
    assert 'NicknameManager.get(user_id, chat_id)' in ai
    assert '_rp_display' in rp and 'NicknameManager.get(user.id, chat_id)' in rp
    assert '("nicknames", UserNickname)' in memory
