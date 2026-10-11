from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fast_local_ai_defaults_and_sequential_unload():
    ai = (ROOT / "bot/ai_client.py").read_text(encoding="utf-8")
    env = (ROOT / "example.env").read_text(encoding="utf-8")
    assert 'fast_mode=flag("AI_FAST_MODE", True)' in ai
    assert 'ollama_keep_alive=(os.getenv("OLLAMA_KEEP_ALIVE", "2m")' in ai
    assert 'ollama_num_ctx=bounded_int("OLLAMA_NUM_CTX", 4096' in ai
    assert 'await self._prepare_ollama_model(model)' in ai
    assert '"keep_alive": "0s"' in ai  # explicit unload path
    assert '"keep_alive": self.config.ollama_keep_alive' in ai
    assert 'AI_FAST_MODE=1' in env
    assert 'OLLAMA_KEEP_ALIVE=2m' in env
    assert 'OLLAMA_NUM_CTX=4096' in env
    assert 'AI_SMART_DIALOGUE=1' in env
    assert 'AI_HISTORY_MESSAGES=10' in env
    assert 'AI_HISTORY_MAX_CHARS=10000' in env
    assert 'AI_MAX_RESPONSE_TOKENS=1100' in env


def test_report_storage_and_commands_are_shipped():
    orm = (ROOT / "bot/sql/orm_tables.py").read_text(encoding="utf-8")
    features = (ROOT / "bot/group_features.py").read_text(encoding="utf-8")
    handlers = (ROOT / "bot/handlers/community.py").read_text(encoding="utf-8")
    assert 'class GroupReport(TableBase):' in orm
    assert 'class GroupReportManager:' in features
    assert 'MAX_REPORTS_PER_DAY = 8' in features
    for command in ("report", "reports", "report_info", "report_done", "report_reject"):
        assert f'Command("{command}")' in handlers
    assert 'message_text=evidence' in handlers
    assert 'await _notify_report_staff(message, row)' in handlers


def test_ai_speed_command_is_present():
    suite = (ROOT / "bot/handlers/suite.py").read_text(encoding="utf-8")
    bot = (ROOT / "bot/bot.py").read_text(encoding="utf-8")
    assert 'Command("ai_speed")' in suite
    assert 'ai.speed_status()' in suite
    assert 'telegram_menu_commands()' in bot
    help_ui = (ROOT / "bot/help_ui.py").read_text(encoding="utf-8")
    assert '("/ai_speed"' in help_ui
