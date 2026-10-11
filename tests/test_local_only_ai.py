from pathlib import Path


def test_local_only_runtime_is_hard_locked_to_ollama():
    root = Path(__file__).resolve().parents[1]
    source = (root / "bot" / "ai_client.py").read_text(encoding="utf-8")
    env = (root / "example.env").read_text(encoding="utf-8")
    setup = (root / "setup.sh").read_text(encoding="utf-8")
    quality = (root / "ai_quality.sh").read_text(encoding="utf-8")

    assert 'local_only=flag("AI_LOCAL_ONLY", True)' in source
    assert 'if self.config.local_only:\n            return ["ollama"]' in source
    assert 'AI_PROVIDER_ORDER=ollama' in env
    assert 'AI_LOCAL_ONLY=1' in env
    assert 'AI_PROVIDER_ORDER="ollama"' in setup
    assert "set_key('AI_PROVIDER_ORDER', 'ollama')" in quality
    assert "set_key('AI_LOCAL_ONLY', '1')" in quality
