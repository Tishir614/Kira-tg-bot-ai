from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from shazamio import Shazam

from bot.media_downloader import MediaDownload, media_downloader


class TrackFinderError(RuntimeError):
    pass


@dataclass(slots=True)
class TrackMatch:
    title: str
    artist: str
    url: str | None
    confidence: float
    exact_version: bool
    downloaded: MediaDownload | None = None


def _fingerprint(path: Path) -> list[int]:
    proc = subprocess.run(
        ["fpcalc", "-json", "-length", "90", str(path)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if proc.returncode != 0:
        raise TrackFinderError("Не удалось построить акустический отпечаток")
    try:
        data = json.loads(proc.stdout)
        return [int(x) for x in data.get("fingerprint", [])]
    except Exception as exc:
        raise TrackFinderError("Chromaprint вернул некорректный отпечаток") from exc


def _best_similarity(source: list[int], candidate: list[int]) -> float:
    """Local Chromaprint alignment. Returns 0..1; robust to a clip cut from a full track."""
    if len(source) < 12 or len(candidate) < 12:
        return 0.0
    # Compare the shorter sequence against sliding windows in the longer one.
    if len(source) > len(candidate):
        source, candidate = candidate, source
    n = len(source)
    # Sampling offsets keeps CPU bounded while still locating arbitrary video excerpts.
    stride = max(1, n // 45)
    best = 0.0
    for off in range(0, max(1, len(candidate) - n + 1), stride):
        window = candidate[off:off + n]
        if len(window) < n:
            break
        # Chromaprint values are 32-bit bitfields. Hamming similarity tolerates re-encoding.
        score = sum(32 - ((a ^ b) & 0xFFFFFFFF).bit_count() for a, b in zip(source, window)) / (32 * n)
        best = max(best, score)
    return best


async def _extract_audio(source: Path) -> Path:
    out = source.with_suffix(".track.wav")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
        "-t", "90", str(out), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    if await proc.wait() != 0 or not out.exists():
        raise TrackFinderError("Не получилось извлечь звук из видео")
    return out


class TrackFinder:
    async def identify(self, video_path: Path) -> TrackMatch:
        audio = await _extract_audio(video_path)
        try:
            raw = await Shazam().recognize(str(audio))
            track = (raw or {}).get("track") or {}
            title = str(track.get("title") or "").strip()
            artist = str(track.get("subtitle") or "").strip()
            if not title:
                raise TrackFinderError("Shazam не смог уверенно определить основу трека")

            source_fp = await asyncio.to_thread(_fingerprint, audio)
            # Search several phrasings. This is important for slowed/reverb/nightcore/remix uploads.
            queries = [f"{artist} {title}", f'"{title}" {artist} remix', f'"{title}" {artist} slowed reverb']
            rows: list[dict] = []
            seen: set[str] = set()
            for q in queries:
                try:
                    for row in await media_downloader.search(q, limit=4):
                        url = str(row.get("url") or "")
                        if url and url not in seen:
                            seen.add(url); rows.append(row)
                except Exception:
                    continue
                if len(rows) >= 8:
                    break

            best_score = 0.0
            best_media: MediaDownload | None = None
            for row in rows[:8]:
                media = None
                try:
                    media = await media_downloader.download(str(row["url"]), audio_only=True)
                    cand_fp = await asyncio.to_thread(_fingerprint, media.path)
                    score = await asyncio.to_thread(_best_similarity, source_fp, cand_fp)
                    if score > best_score:
                        if best_media:
                            best_media.cleanup()
                        best_media, best_score = media, score
                        media = None
                except Exception:
                    pass
                finally:
                    if media:
                        media.cleanup()

            # Conservative thresholds: never call a merely plausible candidate exact.
            exact = best_score >= 0.72
            return TrackMatch(
                title=title, artist=artist, url=(best_media.webpage_url if best_media else None),
                confidence=best_score, exact_version=exact, downloaded=best_media,
            )
        finally:
            audio.unlink(missing_ok=True)


track_finder = TrackFinder()
