import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_activity_helpers():
    tree = ast.parse((ROOT / "bot/group_features.py").read_text(encoding="utf-8"))
    wanted = {"activity_level_for_xp", "activity_progress"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    scope = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<activity_helpers>", "exec"), scope)
    return scope["activity_level_for_xp"], scope["activity_progress"]


def test_activity_level_curve():
    level, _ = _load_activity_helpers()
    assert level(0) == 1
    assert level(99) == 1
    assert level(100) == 2
    assert level(299) == 2
    assert level(300) == 3
    assert level(600) == 4


def test_activity_progress_is_stable():
    _, progress = _load_activity_helpers()
    assert progress(0) == (1, 0, 100)
    assert progress(100) == (2, 0, 200)
    assert progress(250) == (2, 150, 200)
    assert progress(300) == (3, 0, 300)


def test_group_tables_and_commands_are_shipped():
    orm = (ROOT / "bot/sql/orm_tables.py").read_text(encoding="utf-8")
    handlers = (ROOT / "bot/handlers/community.py").read_text(encoding="utf-8")
    assert 'class GroupActivity(TableBase):' in orm
    assert 'class GroupConversationSettings(TableBase):' in orm
    assert 'class GroupReport(TableBase):' in orm
    for command in ("activity", "myactivity", "warn", "ban", "mute", "modlog", "recovery", "report", "reports"):
        assert f'Command("{command}")' in handlers
