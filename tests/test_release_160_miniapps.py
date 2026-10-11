from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_separate_apps_and_chat():
    panel=(ROOT/'bot/web_panel.py').read_text()
    kira=(ROOT/'bot/mini_app.py').read_text()
    dnd=(ROOT/'bot/dnd_app.py').read_text()
    assert '@app.get("/dnd", response_class=HTMLResponse)' in panel
    assert 'DND_MINI_APP_HTML' in panel and '/api/kira/chat' in panel
    assert 'id="chat"' in kira and 'sendChat()' in kira
    assert '/api/dnd/character' in dnd and 'telegram-web-app.js' in dnd
def test_known_chromaprint_package_crash_fixed():
    docker=(ROOT/'Dockerfile').read_text()
    assert 'libchromaprint-tools' in docker
    assert ' chromaprint-tools ' not in docker
def test_upgrade_preserves_volumes():
    s=(ROOT/'upgrade_1_6.sh').read_text()
    assert 'down -v' not in s and 'docker compose up -d' in s
