from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_help_and_private_support_flow_are_shipped():
    help_ui = (ROOT / "bot/help_ui.py").read_text(encoding="utf-8")
    commands = (ROOT / "bot/handlers/commands.py").read_text(encoding="utf-8")
    fsm = (ROOT / "bot/handlers/fsm.py").read_text(encoding="utf-8")
    states = (ROOT / "bot/fsm.py").read_text(encoding="utf-8")
    config = (ROOT / "bot/config.py").read_text(encoding="utf-8")
    assert 'Command("help")' in commands
    assert 'Command("support")' in commands
    assert 'build_help_pages' in commands
    assert 'html.escape(command)' in help_ui
    assert 'except TelegramBadRequest' in commands
    assert 'SUPPORT_CHAT_ID' in config
    assert '@kira26481' in config
    assert 'callback_data="support:start"' in help_ui
    assert 'class SupportTicket' in states
    assert 'process_support_question' in fsm
    assert 'Command("support_reply")' in commands


def test_reply_context_and_smart_dialogue_are_shipped():
    suite = (ROOT / "bot/handlers/suite.py").read_text(encoding="utf-8")
    ai = (ROOT / "bot/ai_client.py").read_text(encoding="utf-8")
    assert 'def _contextual_prompt' in suite
    assert 'Контекст Telegram reply' in suite
    assert 'AI_SMART_DIALOGUE' in ai
    assert 'def _answer_issue' in ai
