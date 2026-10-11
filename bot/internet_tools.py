from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import logging
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import aiohttp

log = logging.getLogger(__name__)


class InternetError(Exception):
    """Базовая ошибка интернет-инструментов."""


class SearchError(InternetError):
    """Поиск не удался ни через один источник."""


class InvalidInternetURL(InternetError):
    """Ссылка отсутствует или использует неподдерживаемую схему."""


class UnsafeInternetURL(InternetError):
    """Ссылка указывает в локальную/служебную сеть и заблокирована."""


class InternetDownloadTooLarge(InternetError):
    """Файл превышает настроенный лимит отправки."""


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(slots=True)
class ImageResult:
    title: str
    image_url: str
    source_url: str = ""


@dataclass(slots=True)
class DownloadedInternetFile:
    path: Path
    filename: str
    content_type: str
    size: int
    source_url: str

    def cleanup(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            log.warning("Не удалось удалить временный файл %s", self.path)


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._active_link = False
        self._active_snippet = False
        self._href = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._last_index: int | None = None

    @staticmethod
    def _class_has(attrs: list[tuple[str, str | None]], needle: str) -> bool:
        classes = next((v or "" for k, v in attrs if k == "class"), "")
        return needle in classes.split()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._class_has(attrs, "result__a"):
            self._active_link = True
            self._title_parts = []
            self._href = next((v or "" for k, v in attrs if k == "href"), "")
        elif self._class_has(attrs, "result__snippet"):
            self._active_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_link:
            self._title_parts.append(data)
        if self._active_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active_link:
            self._active_link = False
            title = " ".join("".join(self._title_parts).split())
            url = _unwrap_duckduckgo_url(self._href)
            if title and url:
                self.results.append(SearchResult(title=title, url=url))
                self._last_index = len(self.results) - 1
        elif self._active_snippet and tag in {"a", "div", "span"}:
            self._active_snippet = False
            snippet = " ".join("".join(self._snippet_parts).split())
            if snippet and self._last_index is not None:
                self.results[self._last_index].snippet = snippet


class _BingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._algo_depth = 0
        self._in_h2 = False
        self._in_link = False
        self._in_p = False
        self._href = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending: SearchResult | None = None

    @staticmethod
    def _class_has(attrs: list[tuple[str, str | None]], needle: str) -> bool:
        classes = next((v or "" for k, v in attrs if k == "class"), "")
        return needle in classes.split()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li" and self._class_has(attrs, "b_algo"):
            self._flush_pending()
            self._algo_depth = 1
            return
        if self._algo_depth:
            self._algo_depth += 1
            if tag == "h2":
                self._in_h2 = True
            elif tag == "a" and self._in_h2 and not self._in_link:
                self._in_link = True
                self._href = next((v or "" for k, v in attrs if k == "href"), "")
                self._title_parts = []
            elif tag == "p" and self._pending is not None:
                self._in_p = True
                self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._title_parts.append(data)
        if self._in_p:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_link and tag == "a":
            self._in_link = False
            title = " ".join("".join(self._title_parts).split())
            if title and self._href.startswith(("http://", "https://")):
                self._pending = SearchResult(title=title, url=self._href)
        elif self._in_h2 and tag == "h2":
            self._in_h2 = False
        elif self._in_p and tag == "p":
            self._in_p = False
            if self._pending is not None:
                self._pending.snippet = " ".join("".join(self._snippet_parts).split())

        if self._algo_depth:
            self._algo_depth -= 1
            if self._algo_depth == 0:
                self._flush_pending()

    def close(self) -> None:
        super().close()
        self._flush_pending()

    def _flush_pending(self) -> None:
        if self._pending is not None:
            self.results.append(self._pending)
            self._pending = None


def _unwrap_duckduckgo_url(value: str) -> str:
    if not value:
        return ""
    value = html_lib.unescape(value)
    if value.startswith("//"):
        value = "https:" + value
    parsed = urlparse(value)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        redirect = parse_qs(parsed.query).get("uddg", [""])[0]
        if redirect:
            return unquote(redirect)
    return value if value.startswith(("http://", "https://")) else ""


def _dedupe_results(results: Iterable[SearchResult], limit: int) -> list[SearchResult]:
    output: list[SearchResult] = []
    seen: set[str] = set()
    for item in results:
        normalized = item.url.rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(item)
        if len(output) >= limit:
            break
    return output


class InternetSearch:
    """Поиск без API-ключа с fallback между DuckDuckGo HTML и Bing HTML."""

    DDG_URL = "https://html.duckduckgo.com/html/"
    BING_URL = "https://www.bing.com/search"

    def __init__(self) -> None:
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        self.timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=15)

    async def image_search(self, query: str, max_results: int = 4) -> list[ImageResult]:
        query = " ".join(query.split()).strip()
        if not query:
            return []
        max_results = max(1, min(max_results, 8))

        def _run() -> list[ImageResult]:
            from ddgs import DDGS
            out: list[ImageResult] = []
            with DDGS(timeout=8) as ddgs:
                for item in ddgs.images(query, max_results=max_results, safesearch="moderate"):
                    image = str(item.get("image") or item.get("thumbnail") or "")
                    if not image.startswith(("http://", "https://")):
                        continue
                    out.append(ImageResult(
                        title=str(item.get("title") or query),
                        image_url=image,
                        source_url=str(item.get("url") or ""),
                    ))
                    if len(out) >= max_results:
                        break
            return out

        return await asyncio.to_thread(_run)

    async def search(self, query: str, max_results: int = 6) -> list[SearchResult]:
        query = " ".join(query.split()).strip()
        if not query:
            return []
        max_results = max(1, min(max_results, 10))

        last_error: Exception | None = None

        # Primary: actively maintained metasearch library. It can aggregate several
        # engines and is much less brittle than scraping a single HTML layout.
        try:
            results = await asyncio.to_thread(self._ddgs, query, max_results)
            results = _dedupe_results(results, max_results)
            if results:
                return results
        except Exception as exc:
            last_error = exc
            log.warning("DDGS search failed; falling back to HTML providers: %s", exc)

        async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
            providers = (self._duckduckgo, self._bing)
            for provider in providers:
                try:
                    results = await provider(session, query, max_results)
                    results = _dedupe_results(results, max_results)
                    if results:
                        return results
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                    last_error = exc
                    log.warning("Web search provider %s failed: %s", provider.__name__, exc)

        raise SearchError(str(last_error or "search providers returned no results"))

    @staticmethod
    def _ddgs(query: str, max_results: int) -> list[SearchResult]:
        from ddgs import DDGS

        raw = DDGS(timeout=8).text(
            query,
            region="ru-ru",
            safesearch="moderate",
            max_results=max_results,
            backend="auto",
        )
        results: list[SearchResult] = []
        for item in raw or []:
            href = str(item.get("href") or item.get("url") or "").strip()
            if not href.startswith(("http://", "https://")):
                continue
            results.append(SearchResult(
                title=str(item.get("title") or href)[:300],
                url=href,
                snippet=str(item.get("body") or item.get("snippet") or "")[:1000],
            ))
        return results

    async def _duckduckgo(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        async with session.post(
            self.DDG_URL,
            data={"q": query, "kl": "wt-wt"},
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            text = await response.text(errors="replace")
        parser = _DuckDuckGoParser()
        parser.feed(text)
        parser.close()
        return parser.results[:max_results]

    async def _bing(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        async with session.get(
            self.BING_URL,
            params={"q": query, "count": str(max_results)},
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            text = await response.text(errors="replace")
        parser = _BingParser()
        parser.feed(text)
        parser.close()
        return parser.results[:max_results]


class InternetDownloader:
    """Потоково скачивает публичный HTTP/HTTPS-файл во временный файл.

    Внутренние, loopback, link-local и прочие непубличные адреса намеренно
    блокируются, чтобы команда не давала доступ к сети/метаданным самого сервера.
    """

    URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
    MAX_REDIRECTS = 6

    def __init__(self) -> None:
        default_limit = "1900" if os.getenv("BOT_API_BASE_URL", "").strip() else "49"
        raw_limit = os.getenv("INTERNET_MAX_DOWNLOAD_MB", default_limit).strip()
        try:
            limit_mb = int(raw_limit)
        except ValueError:
            limit_mb = 49
        self.max_bytes = max(1, min(limit_mb, 2000)) * 1024 * 1024
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
        self.timeout = aiohttp.ClientTimeout(total=180, connect=15, sock_read=60)

    @classmethod
    def extract_url(cls, text: str | None) -> str | None:
        if not text:
            return None
        match = cls.URL_RE.search(text)
        if not match:
            return None
        return match.group(0).rstrip(".,!?;:)]}'")

    async def download(self, url: str) -> DownloadedInternetFile:
        current_url = self._normalize_url(url)
        temp_path: Path | None = None

        async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
            for _ in range(self.MAX_REDIRECTS + 1):
                await self._validate_public_url(current_url)
                try:
                    response = await session.get(current_url, allow_redirects=False)
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    raise InternetError(str(exc)) from exc

                async with response:
                    self._validate_peer(response)
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise InternetError("redirect without Location")
                        current_url = urljoin(current_url, location)
                        continue

                    if response.status < 200 or response.status >= 300:
                        raise InternetError(f"HTTP {response.status}")

                    declared_size = response.headers.get("Content-Length", "")
                    if declared_size.isdigit() and int(declared_size) > self.max_bytes:
                        raise InternetDownloadTooLarge()

                    filename = self._filename(response, current_url)
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
                    content_type = content_type.split(";", 1)[0].strip() or "application/octet-stream"

                    fd, tmp_name = tempfile.mkstemp(prefix="kira_web_", suffix="_" + filename)
                    os.close(fd)
                    temp_path = Path(tmp_name)
                    size = 0
                    try:
                        with temp_path.open("wb") as output:
                            async for chunk in response.content.iter_chunked(512 * 1024):
                                size += len(chunk)
                                if size > self.max_bytes:
                                    raise InternetDownloadTooLarge()
                                output.write(chunk)
                    except BaseException:
                        temp_path.unlink(missing_ok=True)
                        raise

                    if size == 0:
                        temp_path.unlink(missing_ok=True)
                        raise InternetError("empty response")

                    return DownloadedInternetFile(
                        path=temp_path,
                        filename=filename,
                        content_type=content_type,
                        size=size,
                        source_url=current_url,
                    )

        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise InternetError("too many redirects")

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").strip()
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise InvalidInternetURL()
        if parsed.username or parsed.password:
            raise InvalidInternetURL()
        return url

    async def _validate_public_url(self, url: str) -> None:
        parsed = urlparse(self._normalize_url(url))
        host = (parsed.hostname or "").lower().rstrip(".")
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise UnsafeInternetURL()

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise InternetError(f"DNS: {exc}") from exc

        if not infos:
            raise InternetError("DNS returned no addresses")

        for info in infos:
            raw_ip = info[4][0]
            try:
                address = ipaddress.ip_address(raw_ip)
            except ValueError as exc:
                raise UnsafeInternetURL() from exc
            if not address.is_global:
                raise UnsafeInternetURL()

    @staticmethod
    def _validate_peer(response: aiohttp.ClientResponse) -> None:
        connection = response.connection
        if connection is None or connection.transport is None:
            return
        peer = connection.transport.get_extra_info("peername")
        if not peer:
            return
        try:
            address = ipaddress.ip_address(peer[0])
        except (ValueError, TypeError):
            raise UnsafeInternetURL()
        if not address.is_global:
            raise UnsafeInternetURL()

    @classmethod
    def _filename(cls, response: aiohttp.ClientResponse, url: str) -> str:
        disposition = response.headers.get("Content-Disposition", "")
        filename = ""

        star_match = re.search(r"filename\*\s*=\s*([^;]+)", disposition, re.IGNORECASE)
        normal_match = re.search(r"filename\s*=\s*(?:\"([^\"]+)\"|([^;]+))", disposition, re.IGNORECASE)
        if star_match:
            filename = star_match.group(1).strip().strip('"')
            if "''" in filename:
                filename = filename.split("''", 1)[1]
            filename = unquote(filename)
        elif normal_match:
            filename = (normal_match.group(1) or normal_match.group(2) or "").strip().strip('"')

        if not filename:
            filename = unquote(Path(urlparse(url).path).name)
        if not filename:
            filename = "download.bin"

        filename = filename.replace("\x00", "")
        filename = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", filename).strip(" .")
        if not filename:
            filename = "download.bin"

        stem, suffix = os.path.splitext(filename)
        if len(filename) > 180:
            suffix = suffix[:16]
            filename = stem[: max(1, 180 - len(suffix))] + suffix
        return filename
