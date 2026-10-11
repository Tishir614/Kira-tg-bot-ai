from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_compose_exposes_web_backend_only_on_loopback():
    text=(ROOT / "compose.yml").read_text(encoding="utf-8")
    assert 'WEB_PANEL_HOST: 0.0.0.0' in text
    assert '"127.0.0.1:8080:8080"' in text

def test_dnd_runtime_is_not_tied_to_admin_panel_toggle():
    text=(ROOT / "bot" / "web_panel.py").read_text(encoding="utf-8")
    assert 'dnd_enabled = bool(os.getenv("KIRA_WEBAPP_URL"' in text
    assert 'if not settings.web_panel_enabled and not dnd_enabled:' in text
