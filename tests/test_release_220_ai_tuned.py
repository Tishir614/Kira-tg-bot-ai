from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = (ROOT / 'bot' / 'ai_client.py').read_text(encoding='utf-8')
ENV = (ROOT / 'example.env').read_text(encoding='utf-8')
COMPOSE = (ROOT / 'compose.yml').read_text(encoding='utf-8')


def test_qwen25_is_default_local_model():
    model = 'hf.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF:Q4_K_M'
    assert f'OLLAMA_MODEL={model}' in ENV
    assert f'OLLAMA_FAST_MODEL={model}' in ENV
    assert f'OLLAMA_MODELS={model}' in ENV
    assert model in AI


def test_local_vision_route_exists():
    assert 'KIRA_VISION_URL' in AI
    assert '/v1/chat/completions' in AI
    assert 'KIRA_VISION_MODEL' in ENV


def test_compose_has_linux_host_gateway_and_no_file_url_interpolation_bug():
    assert 'host.docker.internal:host-gateway' in COMPOSE
    assert '"$FILE"' not in COMPOSE
    assert '"$URL"' not in COMPOSE


def test_persona_allows_contextual_profanity_without_star_censoring():
    assert 'Не заменяй живую речь звёздочками автоматически' in AI
    assert 'можешь употреблять его естественно' in AI
