from __future__ import annotations

import io
import json
import zipfile

import pytest

from bot.file_tools import FileAnalysisError, extract_text


def test_json_pretty_print():
    raw = json.dumps({"hello": "world"}, ensure_ascii=False).encode()
    text = extract_text("x.json", raw)
    assert '"hello": "world"' in text


def test_zip_lists_and_reads_safe_text():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("readme.txt", "hello kira")
    text = extract_text("demo.zip", bio.getvalue())
    assert "readme.txt" in text
    assert "hello kira" in text


def test_unknown_format_rejected():
    with pytest.raises(FileAnalysisError):
        extract_text("demo.exe", b"MZ")
