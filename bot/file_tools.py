from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader


class FileAnalysisError(RuntimeError):
    pass


TEXT_EXTS = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".csv",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".html", ".css", ".sql",
}


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(filename: str, data: bytes, *, max_chars: int = 50000) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_EXTS:
        text = _decode(data)
        if suffix == ".json":
            try:
                obj = json.loads(text)
                text = json.dumps(obj, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        elif suffix == ".csv":
            try:
                rows = list(csv.reader(io.StringIO(text)))[:200]
                text = "\n".join(" | ".join(row[:20]) for row in rows)
            except csv.Error:
                pass
        return text[:max_chars]

    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        chunks: list[str] = []
        for idx, page in enumerate(reader.pages[:80], 1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                chunks.append(f"--- Страница {idx} ---\n{text}")
            if sum(map(len, chunks)) >= max_chars:
                break
        return "\n\n".join(chunks)[:max_chars]

    if suffix == ".docx":
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text[:max_chars]

    if suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000:
                raise FileAnalysisError("В архиве слишком много файлов")
            total_unpacked = sum(max(0, i.file_size) for i in infos)
            if total_unpacked > 200 * 1024 * 1024:
                raise FileAnalysisError("Распакованный архив слишком большой")
            lines = ["Содержимое ZIP:"]
            for info in infos[:300]:
                lines.append(f"- {info.filename} ({info.file_size} байт)")
            # Не распаковываем архив на диск. Читаем лишь несколько безопасных текстовых файлов.
            text_budget = max_chars - sum(map(len, lines))
            for info in infos:
                if text_budget <= 0:
                    break
                suffix_inner = Path(info.filename).suffix.lower()
                if info.is_dir() or suffix_inner not in TEXT_EXTS or info.file_size > 2 * 1024 * 1024:
                    continue
                try:
                    content = _decode(archive.read(info))[:8000]
                except Exception:
                    continue
                block = f"\n--- {info.filename} ---\n{content}"
                lines.append(block)
                text_budget -= len(block)
            return "\n".join(lines)[:max_chars]

    raise FileAnalysisError(f"Формат {suffix or 'без расширения'} пока не поддерживается")
