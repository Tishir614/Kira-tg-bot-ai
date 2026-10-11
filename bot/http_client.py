from __future__ import annotations

import asyncio

import aiohttp


class SharedHTTPClient:
    """Lazy shared aiohttp session for small public API requests.

    Long-running file downloads keep their dedicated sessions/timeouts, while
    weather/currency/news/music/search calls reuse a bounded connection pool.
    """

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        async with self._lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=64,
                    limit_per_host=12,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=30, connect=8, sock_read=20),
                    trust_env=False,
                )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None


http_client = SharedHTTPClient()
