from __future__ import annotations

from pathlib import Path

from bot.command_aliases import rewrite_command_text

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_120() -> None:
    assert 'version = "1.2.0"' in (ROOT / 'pyproject.toml').read_text('utf-8')


def test_new_profile_commands_keep_russian_interface() -> None:
    assert rewrite_command_text('/пол женский') == '/gender женский'
    assert rewrite_command_text('/косметика') == '/cosmetics'
    assert rewrite_command_text('/цвет_ника #FF66CC') == '/nick_color #FF66CC'
    assert rewrite_command_text('/титул Ночной лис') == '/title Ночной лис'
    assert rewrite_command_text('/значок ⭐') == '/badge ⭐'
    assert rewrite_command_text('/тема_профиля midnight') == '/profile_theme midnight'


def test_mini_app_is_one_page_and_old_dnd_redirects() -> None:
    panel = (ROOT / 'bot' / 'web_panel.py').read_text('utf-8')
    mini = (ROOT / 'bot' / 'mini_app.py').read_text('utf-8')
    assert 'request.url.path in {"/dnd", "/kira"}' in panel
    assert 'RedirectResponse(url="/kira#dnd"' in panel
    for section in ('id="home"', 'id="profile"', 'id="shop"', 'id="dnd"', 'id="commands"', 'id="memory"'):
        assert section in mini


def test_image_service_is_on_demand_quantized() -> None:
    compose = (ROOT / 'compose.yml').read_text('utf-8')
    dockerfile = (ROOT / 'deploy' / 'local-image' / 'Dockerfile').read_text('utf-8')
    server = (ROOT / 'deploy' / 'local-image' / 'server.py').read_text('utf-8')
    client = (ROOT / 'bot' / 'image_generation.py').read_text('utf-8')
    assert 'v1-5-pruned_Q4_0.gguf' in compose
    assert 'sd-cli' in dockerfile and 'server.py' in dockerfile
    assert 'COPY --from=build /src/build/bin /opt/sd/bin' in dockerfile
    assert 'DGGML_CPU_ALL_VARIANTS=ON' in dockerfile
    assert 'subprocess.run' in server and '"/generate"' in server
    assert 'f"{self.base_url}/generate"' in client


def test_piper_18_cli_and_legacy_fallback_present() -> None:
    ai = (ROOT / 'bot' / 'ai_client.py').read_text('utf-8')
    setup = (ROOT / 'setup.sh').read_text('utf-8')
    assert 'sys.executable, "-m", "piper"' in ai
    assert '"-f", str(wav)' in ai
    assert '"--", clean' in ai
    assert '"--output_file", str(wav)' in ai
    assert "python -m piper \\\n    -m ru_RU-irina-medium" in setup
    assert "-f /tmp/kira-piper-check.wav -- 'Привет, это Кира.'" in setup


def test_random_who_uses_real_group_activity() -> None:
    suite = (ROOT / 'bot' / 'handlers' / 'suite.py').read_text('utf-8')
    assert 'кира[,! ]+кто' in suite
    assert 'GroupActivityManager.top(message.chat.id, 50)' in suite
    assert 'random.choice(candidates)' in suite
    assert 'NicknameManager.get(chosen.user_id, message.chat.id)' in suite
