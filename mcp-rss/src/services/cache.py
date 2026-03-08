"""In-memory LRU feed cache with TTL expiry and background cleanup."""

from __future__ import annotations
import asyncio
from collections import OrderedDict
from typing import Optional

from ..config import config
from ..logger import logger
from ..types import CacheEntry, FeedResult
from ..utils.date import now_ms


class FeedCache:
    """Thread-safe async LRU cache for RSS feed results."""

    def __init__(self) -> None:
        # OrderedDict used as LRU: most-recently-used at the right end
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start background cleanup loop (call once event loop is running)."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def destroy(self) -> None:
        """Cancel cleanup task and clear the cache."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str) -> Optional[FeedResult]:
        """Return cached feed data if present and not expired, else None."""
        entry = self._cache.get(url)
        if entry is None:
            return None
        if now_ms() > entry.expires_at:
            del self._cache[url]
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(url)
        return entry.data

    def get_metadata(self, url: str) -> Optional[dict]:
        """Return ETag / Last-Modified metadata without touching the data."""
        entry = self._cache.get(url)
        if entry is None:
            return None
        return {"etag": entry.etag, "last_modified": entry.last_modified}

    def set(self, url: str, data: FeedResult, ttl_ms: Optional[int] = None) -> None:
        """Store a feed result, evicting the LRU entry if at capacity."""
        expires_at = now_ms() + (ttl_ms if ttl_ms is not None else config.rss_cache_ttl)
        entry = CacheEntry(
            data=data,
            expires_at=expires_at,
            etag=data.etag,
            last_modified=data.last_modified,
        )
        self._cache[url] = entry
        self._cache.move_to_end(url)

        if len(self._cache) > config.rss_cache_max_size:
            evicted_url, _ = self._cache.popitem(last=False)
            logger.debug(f"Evicted LRU cache entry: {evicted_url}")

        logger.debug(
            f"Cached feed: {url}, expires_at: {expires_at}"
        )

    def has(self, url: str) -> bool:
        """Return True if any entry exists (even if expired)."""
        return url in self._cache

    def delete(self, url: str) -> None:
        self._cache.pop(url, None)

    def clear(self) -> None:
        self._cache.clear()
        logger.info("Feed cache cleared")

    def get_stats(self) -> dict:
        return {
            "size": len(self._cache),
            "urls": list(self._cache.keys()),
        }

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    async def _cleanup_loop(self) -> None:
        interval = config.rss_cache_cleanup_interval / 1000  # convert ms → s
        while True:
            await asyncio.sleep(interval)
            self._evict_expired()

    def _evict_expired(self) -> None:
        now = now_ms()
        expired = [url for url, e in self._cache.items() if now > e.expires_at]
        for url in expired:
            del self._cache[url]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entries")


# Module-level singleton
feed_cache = FeedCache()
