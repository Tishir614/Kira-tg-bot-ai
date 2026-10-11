from __future__ import annotations

import asyncio
import html
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot import log

router = Router(name="kira-omniget-sketchforge")


def _arg(message: Message) -> str:
    parts = (message.text or "").strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _safe_url(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return value.strip()


async def _run(*args: str, timeout: int = 1800) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "NO_COLOR": "1"},
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "timeout"
    return proc.returncode or 0, out.decode("utf-8", errors="replace")[-12000:]


def _omniget_bin() -> str | None:
    configured = os.getenv("OMNIGET_BIN", "omniget").strip() or "omniget"
    return shutil.which(configured) or (configured if Path(configured).is_file() else None)


@router.message(Command("omniget", "скачать", "download"))
async def omniget_download(message: Message) -> None:
    url = _safe_url(_arg(message))
    if not url:
        await message.reply(
            "📥 <b>OmniGet</b>\n"
            "<code>/скачать https://ссылка</code> — скачать видео/файл\n"
            "<code>/аудио https://ссылка</code> — только аудио\n"
            "<code>/инфо https://ссылка</code> — посмотреть информацию."
        )
        return
    await _download(message, url, audio_only=False)


@router.message(Command("audio_get", "аудио"))
async def omniget_audio(message: Message) -> None:
    url = _safe_url(_arg(message))
    if not url:
        await message.reply("🎵 Использование: <code>/аудио https://ссылка</code>")
        return
    await _download(message, url, audio_only=True)


@router.message(Command("omniget_info", "инфо"))
async def omniget_info(message: Message) -> None:
    url = _safe_url(_arg(message))
    if not url:
        await message.reply("ℹ️ Использование: <code>/инфо https://ссылка</code>")
        return
    binary = _omniget_bin()
    if not binary:
        await message.reply("OmniGet CLI не установлен в этом контейнере (он необязателен). Для обычных загрузок используй /download; чтобы поставить OmniGet, пересобери образ с INSTALL_OMNIGET=1.")
        return
    wait = await message.reply("🔎 OmniGet изучает ссылку…")
    code, output = await _run(binary, "info", url, timeout=120)
    if code:
        await wait.edit_text("OmniGet не смог прочитать ссылку:\n<pre>" + html.escape(output[-2500:]) + "</pre>")
        return
    await wait.edit_text("📦 <b>OmniGet</b>\n<pre>" + html.escape(output[-3500:]) + "</pre>")


async def _download(message: Message, url: str, *, audio_only: bool) -> None:
    binary = _omniget_bin()
    if not binary:
        await message.reply("OmniGet CLI не установлен в этом контейнере (он необязателен). Для обычных загрузок используй /download; чтобы поставить OmniGet, пересобери образ с INSTALL_OMNIGET=1.")
        return
    wait = await message.reply("📥 OmniGet скачивает…")
    with tempfile.TemporaryDirectory(prefix="kira-omniget-") as tmp:
        before = set(Path(tmp).rglob("*"))
        args = [binary, "download", url, "-o", tmp]
        if audio_only:
            args.append("--audio-only")
        code, output = await _run(*args)
        files = [p for p in Path(tmp).rglob("*") if p.is_file() and p not in before]
        if code or not files:
            await wait.edit_text("❌ OmniGet не завершил загрузку:\n<pre>" + html.escape(output[-2200:]) + "</pre>")
            return
        path = max(files, key=lambda p: p.stat().st_size)
        # Telegram Bot API/cloud limits can differ by deployment. Fail cleanly rather than exhausting RAM.
        max_mb = int(os.getenv("OMNIGET_TELEGRAM_MAX_MB", "49"))
        if path.stat().st_size > max_mb * 1024 * 1024:
            await wait.edit_text(
                f"✅ OmniGet скачал <b>{html.escape(path.name)}</b>, но файл больше лимита отправки Киры ({max_mb} МБ). "
                "Увеличь OMNIGET_TELEGRAM_MAX_MB, если твой Bot API поддерживает большие файлы."
            )
            return
        try:
            upload = FSInputFile(path, filename=path.name)
            if audio_only:
                try:
                    await message.answer_audio(upload, caption="🎵 Загружено через OmniGet")
                except Exception:
                    await message.answer_document(upload, caption="🎵 Загружено через OmniGet")
            else:
                await message.answer_document(upload, caption="📦 Загружено через OmniGet")
            await wait.delete()
        except Exception:
            log.exception("OmniGet Telegram upload failed")
            await wait.edit_text("Файл скачан, но Telegram не принял его. Проверь лимит размера Bot API.")


def _sketchforge_url() -> str:
    explicit = os.getenv("SKETCHFORGE_PUBLIC_URL", "").strip()
    if explicit:
        return explicit
    base = os.getenv("KIRA_WEBAPP_URL", "").strip()
    if base.startswith("https://"):
        root = base.split("/kira", 1)[0].rstrip("/")
        return root + "/sketchforge/"
    return ""


@router.message(Command("sketchforge", "3d"))
async def sketchforge_cmd(message: Message) -> None:
    url = _sketchforge_url()
    if not url:
        await message.reply(
            "🧊 SketchForge подключён, но для Telegram нужна публичная HTTPS-ссылка. "
            "Укажи <code>SKETCHFORGE_PUBLIC_URL=https://твой-домен/sketchforge/</code>."
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🧊 Открыть SketchForge 3D", web_app=WebAppInfo(url=url))
    ]])
    await message.reply(
        "🧊 <b>SketchForge 3D</b>\nСоздавай и редактируй 3D-модели прямо из интерфейса Киры.",
        reply_markup=keyboard,
    )
