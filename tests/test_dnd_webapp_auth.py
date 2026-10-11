from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dnd_page_loads_official_telegram_webapp_sdk():
    panel = (ROOT / "bot/web_panel.py").read_text(encoding="utf-8")
    mini = (ROOT / "bot/mini_app.py").read_text(encoding="utf-8")
    assert 'https://telegram.org/js/telegram-web-app.js' in mini
    assert 'X-Telegram-Init-Data' in mini
    assert 'RedirectResponse(url="/kira#dnd"' in panel


def test_dnd_route_does_not_force_deny_framing():
    source = (ROOT / "bot/web_panel.py").read_text(encoding="utf-8")
    assert 'request.url.path in {"/dnd", "/kira"}' in source
    assert 'frame-ancestors https://web.telegram.org https://*.telegram.org' in source


def test_dnd_security_middleware_does_not_use_mutableheaders_pop():
    source = (ROOT / "bot/web_panel.py").read_text(encoding="utf-8")
    assert 'response.headers.pop(' not in source
