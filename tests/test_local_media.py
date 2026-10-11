from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_cloud_tts_or_image_provider_in_runtime():
    ai = (ROOT / "bot/ai_client.py").read_text(encoding="utf-8")
    image = (ROOT / "bot/image_generation.py").read_text(encoding="utf-8")
    assert "edge_tts" not in ai
    assert "gen.pollinations.ai" not in ai
    assert "pollinations" not in image.lower()
    assert "stable-diffusion.cpp" in image
    assert "piper" in ai.lower()


def test_redis_fsm_stores_json_safe_primitives():
    core = (ROOT / "bot/core.py").read_text(encoding="utf-8")
    fsm = (ROOT / "bot/handlers/fsm.py").read_text(encoding="utf-8")
    assert "bot_message=m" not in core
    assert "bot_message_id=m.message_id" in core
    assert "Character(**raw)" in fsm
    assert "state.update_data(character=character)" in fsm
    assert "Character(name=" not in fsm


def test_local_image_service_is_private_and_profiled():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert 'profiles: ["image"]' in compose
    assert "kira-image-models:/models" in compose
    image = (ROOT / "bot/image_generation.py").read_text(encoding="utf-8")
    assert "http://local-image:7860" in image
    local_image_block = compose.split("  local-image:\n", 1)[1].split("\n  nginx:", 1)[0]
    assert "ports:" not in local_image_block
