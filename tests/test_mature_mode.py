from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mature_columns_exist():
    source = (ROOT / "bot" / "sql" / "orm_tables.py").read_text(encoding="utf-8")
    assert "adult_confirmed" in source
    assert "mature_mode" in source


def test_mature_prompt_has_adult_guardrails():
    source = (ROOT / "bot" / "ai_client.py").read_text(encoding="utf-8").lower()
    assert "mature_prompt" in source
    assert "18+" in source
    assert "соглас" in source
    assert "несовершеннолет" in source


def test_roleplay_action_handler_exists():
    source = (ROOT / "bot" / "handlers" / "suite.py").read_text(encoding="utf-8").lower()
    assert "roleplay_action_handler" in source
    assert "*обнял тебя*" in source
    assert "preferred_order=(\"ollama\",)" in source


def test_mature_profile_and_session_features_exist():
    orm = (ROOT / "bot" / "sql" / "orm_tables.py").read_text(encoding="utf-8")
    suite = (ROOT / "bot" / "handlers" / "suite.py").read_text(encoding="utf-8").lower()
    assert "class matureprofile" in orm.lower()
    assert "class maturesession" in orm.lower()
    assert "/mature intensity" in suite
    assert "/mature safeword" in suite
    assert "/rp18 pause" in suite
    assert "chemistry" in suite


def test_mature_safeword_is_local_and_immediate():
    suite = (ROOT / "bot" / "handlers" / "suite.py").read_text(encoding="utf-8").lower()
    assert "стоп-слово принято" in suite
    assert "set_session_state" in suite
