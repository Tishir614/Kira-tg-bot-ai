import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_classify():
    tree = ast.parse((ROOT / "bot/recovery.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RecoveryRuntime")
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "classify")
    node.decorator_list = []
    scope = {"BaseException": BaseException}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<recovery_classify>", "exec"), scope)
    return scope["classify"]


def test_recovery_classification():
    classify = _load_classify()
    assert classify(RuntimeError("database is locked")) == "database"
    assert classify(ConnectionError("redis connection refused")) == "connection"
    assert classify(TimeoutError("timed out")) == "timeout"
    assert classify(TypeError("Object of type Message is not JSON serializable")) == "serialization"
    assert classify(RuntimeError("ordinary failure")) == "application"


def test_recovery_never_rewrites_source_code():
    source = (ROOT / "bot/recovery.py").read_text(encoding="utf-8")
    assert "os._exit(75)" in source
    assert "AUTO_RECOVERY_RESTART" in source
    assert "Path(__file__).write" not in source
    assert "exec(" not in source
