from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FILE_HASHES = {
    "bot/handlers/masturbate/__init__.py": "041e745e09fb543ce4c5ef2d22a6bc4ff261ac3c11f0d82b080d3dfdacc3b844",
    "bot/handlers/masturbate/callbacks.py": "a49cd120b6f28626a1ec4a3247e33866c51e2cc3cb6b450aaf99dd10658433c6",
    "bot/handlers/masturbate/commands.py": "b716aa564579ead897cc2a063c12ec36abdac24fe95a231cf47931f5104e5b8d",
}

def test_masturbate_module_is_byte_for_byte_frozen():
    for relative, expected in EXPECTED_FILE_HASHES.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, f"Frozen command changed: {relative}"


def test_masturbate_database_contract_is_preserved():
    # The shared SQL module legitimately evolves with profile/economy migrations,
    # so freeze the mature feature's data contract instead of the entire database file.
    sql = (ROOT / "bot/sql/__init__.py").read_text(encoding="utf-8")
    orm = (ROOT / "bot/sql/orm_tables.py").read_text(encoding="utf-8")
    assert "async def update_masturbate_stats" in sql
    assert "async def get_top_penis" in sql
    assert "penis_len=penis_len" in sql
    assert "masturbate_cooldown_until=cooldown_until" in sql
    assert "penis_len: Mapped[float]" in orm
    assert "masturbate_cooldown_until: Mapped[int]" in orm
