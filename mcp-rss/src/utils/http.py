"""Async HTTP client with rate limiting and redirect handling."""

from __future__ import annotations
import asyncio
import time

import httpx

from ..config import config
from ..logger import logger

_DEFAULT_HEADERS = {
    "User-Agent": config.rss_user_agent,
    "Accept": (
        "application/rss+xml, application/atom+xml, "
        "application/xml, text/xml, */*"
    ),
}


class RateLimitedClient:
    """Thin async HTTP client that enforces a per-minute request limit."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._requests_this_minute: int = 0
        self._minute_start: float = time.monotonic()

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        follow_redirects: bool | None = None,
    ) -> httpx.Response:
        await self._throttle()

        merged_headers = {**_DEFAULT_HEADERS, **(headers or {})}
        timeout = (timeout_ms or config.rss_request_timeout) / 1000
        redirects = (
            follow_redirects
            if follow_redirects is not None
            else config.rss_follow_redirects
        )

        async with httpx.AsyncClient(
            follow_redirects=redirects,
            timeout=timeout,
        ) as client:
            response = await client.get(url, headers=merged_headers)
            return response

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._minute_start
            if elapsed >= 60.0:
                self._requests_this_minute = 0
                self._minute_start = now

            if self._requests_this_minute >= config.rss_rate_limit_per_minute:
                wait = 60.0 - elapsed
                logger.debug(f"Rate limit reached, waiting {wait:.1f}s")
                await asyncio.sleep(wait)
                self._requests_this_minute = 0
                self._minute_start = time.monotonic()

            self._requests_this_minute += 1


http_client = RateLimitedClient()
