from pathlib import Path


def test_local_models_are_sequential_and_memory_safe():
    root = Path(__file__).resolve().parents[1]
    ai = (root / "bot" / "ai_client.py").read_text(encoding="utf-8")
    setup = (root / "setup.sh").read_text(encoding="utf-8")
    env = (root / "example.env").read_text(encoding="utf-8")

    assert '("qwen3.5:2b-q4_K_M", "qwen3:1.7b")' in ai
    assert '"keep_alive": "0s"' in ai
    assert 'for model in models:' in ai
    assert 'OLLAMA_MODELS="qwen3.5:2b-q4_K_M,qwen3:1.7b"' in setup
    assert 'OLLAMA_MODELS=qwen3.5:2b-q4_K_M,qwen3:1.7b' in env
    assert 'AI_PROVIDER_ORDER=ollama' in env
    assert 'AI_LOCAL_ONLY=1' in env
    assert 'AI_DELIBERATE_MODE=1' in env
    assert 'AI_REVIEW_PASS=1' in env
