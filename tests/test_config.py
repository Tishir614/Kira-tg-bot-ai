from __future__ import annotations

from bot.config import Settings


def test_settings_bounds(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REQUEST_LIMIT", "99999")
    monkeypatch.setenv("REQUEST_WINDOW_SECONDS", "0")
    monkeypatch.setenv("MAX_CONCURRENT_AI", "0")
    monkeypatch.setenv("FILE_ANALYSIS_MAX_MB", "999")
    cfg = Settings.from_env()
    assert cfg.request_limit == 300
    assert cfg.request_window_seconds == 2
    assert cfg.max_concurrent_ai == 1
    assert cfg.file_analysis_max_mb == 100


def test_panel_requires_strong_token(monkeypatch):
    monkeypatch.setenv("TOKEN", "123:abc")
    monkeypatch.setenv("WEB_PANEL_ENABLED", "1")
    monkeypatch.setenv("PANEL_TOKEN", "short")
    cfg = Settings.from_env()
    assert any("PANEL_TOKEN" in item for item in cfg.validate())


def test_api_id_hash_must_be_pair(monkeypatch):
    monkeypatch.setenv("TOKEN", "123:abc")
    monkeypatch.setenv("API_ID", "123")
    monkeypatch.delenv("API_HASH", raising=False)
    cfg = Settings.from_env()
    assert any("API_ID" in item for item in cfg.validate())


def test_panel_rejects_example_placeholder(monkeypatch):
    monkeypatch.setenv("TOKEN", "123:abc")
    monkeypatch.setenv("WEB_PANEL_ENABLED", "1")
    monkeypatch.setenv("PANEL_TOKEN", "change_me_to_a_long_random_secret")
    cfg = Settings.from_env()
    assert any("PANEL_TOKEN" in item for item in cfg.validate())
