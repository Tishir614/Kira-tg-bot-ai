from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_profile_and_economy_upgrade_is_present():
    orm = read("bot/sql/orm_tables.py")
    sql = read("bot/sql/__init__.py")
    suite = read("bot/handlers/suite.py")
    help_ui = read("bot/help_ui.py")
    assert 'last_work_at: Mapped[int]' in orm
    assert 'bio: Mapped[str]' in orm
    assert 'async def set_bio' in sql
    assert 'async def work' in sql
    assert 'async def transfer_coins' in sql
    for command in ("bio", "wallet", "work", "pay", "richlist"):
        assert f'Command("{command}")' in suite
        assert f'("/{command}' in help_ui


def test_group_fun_upgrade_is_present():
    community = read("bot/handlers/community.py")
    help_ui = read("bot/help_ui.py")
    for command in ("who", "pair", "topic", "chatmood"):
        assert f'Command("{command}")' in community
        assert f'("/{command}' in help_ui
    assert 'GroupActivityManager.top' in community


def test_local_ai_deliberation_and_review_are_present():
    ai = read("bot/ai_client.py")
    quality = read("ai_quality.sh")
    assert 'qwen3.5:2b-q4_K_M' in ai
    assert 'def _is_complex_prompt' in ai
    assert 'payload["think"] = bool(think)' in ai
    assert 'self.config.review_pass and complex_request' in ai
    assert 'AI_DELIBERATE_MODE' in ai
    assert 'AI_REVIEW_PASS' in ai
    assert 'PRIMARY="qwen3.5:2b-q4_K_M"' in quality
