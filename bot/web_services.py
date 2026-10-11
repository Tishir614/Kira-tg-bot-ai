from __future__ import annotations

import asyncio
import html
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin

import aiohttp

from bot.ai_client import ai
from bot.http_client import http_client
from bot.internet_tools import InternetDownloader, InternetSearch, SearchResult


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "canvas"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


async def _fetch_text(url: str, *, max_chars: int = 12000) -> str:
    """Fetch a bounded public text page, re-validating every redirect."""
    guard = InternetDownloader()
    try:
        current = guard._normalize_url(url)
    except Exception:
        return ""

    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
    headers = {
        "User-Agent": "Mozilla/5.0 KiraBot/3.0",
        "Accept-Language": "ru,en;q=0.8",
    }
    max_bytes = 1024 * 1024
    session = await http_client.get()
    for _ in range(6):
        try:
            await guard._validate_public_url(current)
            response = await session.get(
                current, allow_redirects=False, timeout=timeout, headers=headers
            )
        except Exception:
            return ""
        async with response:
            try:
                guard._validate_peer(response)
            except Exception:
                return ""
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    return ""
                current = urljoin(current, location)
                continue
            if response.status >= 400:
                return ""
            ctype = response.headers.get("Content-Type", "").lower()
            if not any(kind in ctype for kind in ("text", "html", "json", "xml")):
                return ""
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                return ""
            payload = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                payload.extend(chunk)
                if len(payload) > max_bytes:
                    break
            charset = response.charset or "utf-8"
            try:
                raw = bytes(payload[:max_bytes]).decode(charset, errors="replace")
            except LookupError:
                raw = bytes(payload[:max_bytes]).decode("utf-8", errors="replace")
            if "html" in ctype:
                parser = _TextExtractor()
                parser.feed(raw)
                text = "\n".join(parser.parts)
            else:
                text = raw
            return text[:max_chars]
    return ""


class ResearchService:
    def __init__(self) -> None:
        self.searcher = InternetSearch()

    async def research(self, query: str, max_sources: int = 5) -> tuple[str, list[SearchResult]]:
        query = " ".join(query.split())[:500]
        try:
            results = await asyncio.wait_for(self.searcher.search(query, max_results=max_sources), timeout=25)
        except Exception:
            results = []
        if not results:
            return (f"🔎 По запросу «{query}» ничего не найдено. Попробуйте уточнить формулировку.", [])
        texts = await asyncio.gather(*[_fetch_text(item.url) for item in results], return_exceptions=True)
        source_blocks: list[str] = []
        for idx, (item, text) in enumerate(zip(results, texts), 1):
            body = "" if isinstance(text, Exception) else str(text)
            if not body:
                body = item.snippet
            source_blocks.append(f"Источник {idx}: {item.title}\nURL: {item.url}\n{body[:6000]}")

        if ai.enabled:
            prompt = (
                f"Исследуй тему: {query}\n\n"
                "Ниже материалы из веб-поиска. Составь фактическую сводку, сравни источники, "
                "отделяй подтверждённое от спорного. Не придумывай сведения. В конце сделай раздел "
                "'Источники' с номерами и URL.\n\n" + "\n\n".join(source_blocks)
            )
            answer = await ai.respond(
                prompt,
                remember=False,
                instructions=(
                    "Ты веб-исследователь. Отвечай только по материалам ниже. Не используй память прошлых "
                    "диалогов, не выдумывай отсутствующие факты, явно отмечай расхождения источников и "
                    "не превращай сниппет поисковика в подтверждённый факт без опоры на текст источника."
                ),
                temperature=ai.config.research_temperature,
                max_tokens=1800,
            )
            return answer, results

        # Fallback без AI: содержательная подборка сниппетов.
        lines = [f"🔎 Результаты исследования: {query}"]
        for i, item in enumerate(results, 1):
            lines.append(f"\n{i}. {item.title}\n{item.snippet}\n{item.url}")
        return "\n".join(lines), results


class WeatherService:
    GEO = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST = "https://api.open-meteo.com/v1/forecast"

    async def current(self, city: str) -> str:
        timeout = aiohttp.ClientTimeout(total=20)
        session = await http_client.get()
        async with session.get(
            self.GEO,
            params={"name": city, "count": 1, "language": "ru", "format": "json"},
            timeout=timeout,
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"Геокодер вернул HTTP {r.status}")
            geo = await r.json(content_type=None)
        results = geo.get("results") or []
        if not results:
            raise RuntimeError("Город не найден")
        place = results[0]
        params = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
        async with session.get(self.FORECAST, params=params, timeout=timeout) as r:
            if r.status >= 400:
                raise RuntimeError(f"Погодный сервис вернул HTTP {r.status}")
            data = await r.json(content_type=None)
        cur = data.get("current") or {}
        codes = {
            0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно",
            45: "туман", 48: "изморозь", 51: "слабая морось", 53: "морось", 55: "сильная морось",
            61: "слабый дождь", 63: "дождь", 65: "сильный дождь", 71: "слабый снег",
            73: "снег", 75: "сильный снег", 80: "ливни", 81: "ливни", 82: "сильные ливни",
            95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
        }
        desc = codes.get(cur.get("weather_code"), "неизвестно")
        name = place.get("name", city)
        country = place.get("country", "")
        return (
            f"🌦 <b>{html.escape(str(name))}{', ' + html.escape(str(country)) if country else ''}</b>\n"
            f"Сейчас: <b>{cur.get('temperature_2m', '?')}°C</b>, ощущается как {cur.get('apparent_temperature', '?')}°C\n"
            f"Погода: {desc}\nВлажность: {cur.get('relative_humidity_2m', '?')}%\n"
            f"Ветер: {cur.get('wind_speed_10m', '?')} км/ч · Осадки: {cur.get('precipitation', '?')} мм"
        )


class CurrencyService:
    URL = "https://api.frankfurter.app/latest"

    async def convert(self, base: str, quote: str, amount: float = 1.0) -> str:
        base, quote = base.upper(), quote.upper()
        timeout = aiohttp.ClientTimeout(total=15)
        session = await http_client.get()
        async with session.get(
            self.URL,
            params={"amount": amount, "from": base, "to": quote},
            timeout=timeout,
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"Сервис валют вернул HTTP {r.status}")
            data = await r.json(content_type=None)
        rates = data.get("rates") or {}
        if quote not in rates:
            raise RuntimeError("Такая валютная пара не поддерживается")
        return f"💱 {amount:g} {base} = <b>{float(rates[quote]):g} {quote}</b>\nДата курса: {data.get('date', '?')}"


class CryptoService:
    SEARCH = "https://api.coingecko.com/api/v3/search"
    PRICE = "https://api.coingecko.com/api/v3/simple/price"

    async def price(self, query: str, currency: str = "usd") -> str:
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"User-Agent": "KiraBot/3.0"}
        session = await http_client.get()
        async with session.get(
            self.SEARCH, params={"query": query}, timeout=timeout, headers=headers
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"CoinGecko HTTP {r.status}")
            search = await r.json(content_type=None)
        coins = search.get("coins") or []
        if not coins:
            raise RuntimeError("Криптовалюта не найдена")
        coin = coins[0]
        coin_id = coin["id"]
        async with session.get(
            self.PRICE,
            params={
                "ids": coin_id,
                "vs_currencies": currency,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
            timeout=timeout,
            headers=headers,
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"CoinGecko HTTP {r.status}")
            data = await r.json(content_type=None)
        row = data.get(coin_id) or {}
        value = row.get(currency)
        change = row.get(f"{currency}_24h_change")
        market = row.get(f"{currency}_market_cap")
        if value is None:
            raise RuntimeError("Цена недоступна")
        sign = "+" if isinstance(change, (int, float)) and change >= 0 else ""
        lines = [
            f"🪙 <b>{html.escape(str(coin.get('name', query)))}</b> ({html.escape(str(coin.get('symbol', '')).upper())})",
            f"Цена: <b>{value:g} {currency.upper()}</b>",
        ]
        if isinstance(change, (int, float)):
            lines.append(f"24ч: {sign}{change:.2f}%")
        if isinstance(market, (int, float)):
            lines.append(f"Капитализация: {market:,.0f} {currency.upper()}")
        return "\n".join(lines)


class NewsService:
    async def search(self, query: str, limit: int = 7) -> list[dict[str, str]]:
        # Google News RSS does not require an API key and returns source links.
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ru&gl=RU&ceid=RU:ru"
        timeout = aiohttp.ClientTimeout(total=20)
        session = await http_client.get()
        async with session.get(
            url, timeout=timeout, headers={"User-Agent": "KiraBot/3.0"}
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"News HTTP {r.status}")
            raw = await r.read()
        if len(raw) > 2 * 1024 * 1024:
            raise RuntimeError("News feed is unexpectedly large")
        root = ET.fromstring(raw)
        out: list[dict[str, str]] = []
        for item in root.findall("./channel/item")[: max(1, min(limit, 20))]:
            out.append({
                "title": html.unescape(item.findtext("title") or "Без заголовка"),
                "link": item.findtext("link") or "",
                "date": item.findtext("pubDate") or "",
            })
        return out


class MusicService:
    ITUNES = "https://itunes.apple.com/search"
    LYRICS = "https://api.lyrics.ovh/v1/{artist}/{title}"
    AUDD = "https://api.audd.io/"

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        timeout = aiohttp.ClientTimeout(total=20)
        session = await http_client.get()
        async with session.get(
            self.ITUNES,
            params={"term": query, "entity": "song", "limit": max(1, min(limit, 20)), "country": "US"},
            timeout=timeout,
        ) as r:
            if r.status >= 400:
                raise RuntimeError(f"Music search HTTP {r.status}")
            data = await r.json(content_type=None)
        return list(data.get("results") or [])

    async def lyrics(self, artist: str, title: str) -> str:
        url = self.LYRICS.format(artist=quote_plus(artist), title=quote_plus(title))
        timeout = aiohttp.ClientTimeout(total=20)
        session = await http_client.get()
        async with session.get(url, timeout=timeout) as r:
            if r.status == 404:
                raise RuntimeError("Текст песни не найден")
            if r.status >= 400:
                raise RuntimeError(f"Lyrics HTTP {r.status}")
            data = await r.json(content_type=None)
        text = str(data.get("lyrics") or "").strip()
        if not text:
            raise RuntimeError("Текст песни не найден")
        return text

    async def recognize(self, data: bytes, filename: str = "sample.mp3") -> dict | None:
        """Recognize a track with AudD when AUDD_API_TOKEN is configured."""
        import os

        token = os.getenv("AUDD_API_TOKEN", "").strip()
        if not token:
            return None
        if len(data) > 20 * 1024 * 1024:
            raise RuntimeError("Фрагмент для распознавания слишком большой (максимум 20 МБ)")
        form = aiohttp.FormData()
        form.add_field("api_token", token)
        form.add_field("return", "apple_music,spotify")
        form.add_field("file", data, filename=filename, content_type="application/octet-stream")
        timeout = aiohttp.ClientTimeout(total=45, connect=10, sock_read=35)
        session = await http_client.get()
        async with session.post(self.AUDD, data=form, timeout=timeout) as r:
            if r.status >= 400:
                raise RuntimeError(f"AudD HTTP {r.status}")
            payload = await r.json(content_type=None)
        if payload.get("status") != "success":
            err = payload.get("error") or {}
            raise RuntimeError(str(err.get("error_message") or "AudD не смог распознать запрос"))
        result = payload.get("result")
        return result if isinstance(result, dict) else None


research_service = ResearchService()
weather_service = WeatherService()
currency_service = CurrencyService()
crypto_service = CryptoService()
news_service = NewsService()
music_service = MusicService()
