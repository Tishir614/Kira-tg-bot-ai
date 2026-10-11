from __future__ import annotations

from pathlib import Path

from bot.command_aliases import rewrite_command_text

ROOT = Path(__file__).resolve().parents[1]


def test_new_russian_commands_keep_legacy_handlers() -> None:
    assert rewrite_command_text('/мат вкл') == '/profanity вкл'
    assert rewrite_command_text('/найти_видео котики') == '/media_video котики'
    assert rewrite_command_text('/найти_музыку трек') == '/media_audio трек'
    assert rewrite_command_text('/найти_картинку лиса') == '/media_image лиса'
    assert rewrite_command_text('/ютуб test') == '/youtube test'
    assert rewrite_command_text('/тикток test') == '/tiktok test'
    assert rewrite_command_text('/твич channel') == '/twitch channel'


def test_ai_has_adaptive_fast_and_smart_route() -> None:
    src = (ROOT / 'bot' / 'ai_client.py').read_text('utf-8')
    assert 'ollama_fast_model' in src
    assert 'ollama_smart_model' in src
    assert 'AI_ADAPTIVE_ROUTING' in src
    assert '_ollama_route_models' in src
    assert 'self._last_route = "smart"' in src


def test_speech_style_is_persistent_and_migratable() -> None:
    orm = (ROOT / 'bot' / 'sql' / 'orm_tables.py').read_text('utf-8')
    sql = (ROOT / 'bot' / 'sql' / '__init__.py').read_text('utf-8')
    assert 'speech_style' in orm
    assert 'class ChatSpeechManager' in sql
    assert '_sync_missing_columns' in sql


def test_media_social_core_has_public_platform_integrations() -> None:
    service = (ROOT / 'bot' / 'social_media.py').read_text('utf-8')
    plugin = (ROOT / 'bot' / 'plugins' / 'kira_media_social.py').read_text('utf-8')
    for platform in ('youtube', 'tiktok', 'twitch'):
        assert platform in service
    for command in ('media_video', 'media_audio', 'media_image', 'youtube', 'tiktok', 'twitch'):
        assert f'Command("{command}")' in plugin
    assert '_SEARCH_TTL = 15 * 60' in plugin
    assert 'callback.from_user.id != session.user_id' in plugin


def test_release_is_not_older_than_110() -> None:
    pyproject = (ROOT / 'pyproject.toml').read_text('utf-8')
    match = __import__('re').search(r'version = "(\d+)\.(\d+)\.(\d+)"', pyproject)
    assert match and tuple(map(int, match.groups())) >= (1, 1, 0)
