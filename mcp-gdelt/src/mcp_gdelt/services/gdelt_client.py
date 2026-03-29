"""Async GDELT API client — DOC 2.0 and GDELT Cloud Media Events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

import httpx

from ..config import config
from ..logger import logger
from ..types import (
    GDELTAPIResponse,
    GDELTMediaEventsResponse,
    GDELTQueryParams,
    SearchArticlesInput,
    SearchImagesInput,
    SearchMediaEventsInput,
)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Non-retryable exception hierarchy
# ---------------------------------------------------------------------------

class GDELTQuotaExceededError(RuntimeError):
    """Monthly API quota exhausted (429 QUOTA_EXCEEDED). Retrying won't help."""


class GDELTAuthError(RuntimeError):
    """Missing or invalid API key (401 MISSING_API_KEY / INVALID_API_KEY)."""


class GDELTAccessDeniedError(RuntimeError):
    """Plan does not include API access (403 API_ACCESS_DENIED)."""


class GDELTRateLimitError(RuntimeError):
    """Transient rate limit (429 RATE_LIMITED). Not retried — caller should back off."""


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    response: Any
    expires_at: float   # monotonic seconds


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GDELTClient:
    """Async wrapper around the GDELT DOC 2.0 and Cloud Media Events APIs.

    Provides:
      • Rate limiting   — enforces GDELT_RATE_LIMIT_INTERVAL between requests
      • Response cache  — TTL-based, keyed on query params (GDELT_CACHE_TTL)
      • Retry / backoff — exponential, with special handling for 429 codes
      • Error taxonomy  — non-retryable errors surfaced immediately
    """

    def __init__(self) -> None:
        self._base_url       = config.gdelt_api_base_url
        self._cloud_base_url = config.gdelt_cloud_base_url
        # Granular timeouts (py-gdelt pattern): only the read phase is slow
        # for GDELT; connect/write/pool are kept tight to surface hangs fast.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=config.gdelt_connect_timeout,
                read=config.gdelt_read_timeout,
                write=config.gdelt_write_timeout,
                pool=config.gdelt_pool_timeout,
            ),
            # Connection pool limits (py-gdelt pattern): cap keep-alive
            # connections so idle sockets don't pile up, while allowing a
            # generous burst ceiling for concurrent tool calls.
            limits=httpx.Limits(
                max_keepalive_connections=config.gdelt_max_keepalive_connections,
                max_connections=config.gdelt_max_connections,
            ),
            headers={"User-Agent": config.gdelt_user_agent},
            follow_redirects=True,
        )
        self._last_request_time: float = 0.0
        self._cache: dict[str, _CacheEntry] = {}
        logger.debug(
            "GDELTClient initialised",
            {
                "doc_url":        self._base_url,
                "cloud_url":      self._cloud_base_url,
                "read_timeout":   config.gdelt_read_timeout,
                "connect_timeout":config.gdelt_connect_timeout,
                "cache_ttl":      config.gdelt_cache_ttl,
                "hist_cache_ttl": config.gdelt_historical_cache_ttl,
                "rate_limit":     config.gdelt_rate_limit_interval,
                "max_keepalive":  config.gdelt_max_keepalive_connections,
                "max_connections":config.gdelt_max_connections,
            },
        )

    # ------------------------------------------------------------------
    # Public tool methods
    # ------------------------------------------------------------------

    async def search_articles(self, inp: SearchArticlesInput) -> GDELTAPIResponse:
        """Return news articles matching the query (GDELT DOC 2.0 API)."""
        logger.info(f"Searching articles: {inp.query}")

        params = GDELTQueryParams(
            query=inp.query,
            mode="ArtList",
            format="JSON",
            maxrecords=inp.max_records or config.gdelt_default_max_records,
            sort=inp.sort or "DateDesc",
            timespan=inp.timespan or config.gdelt_default_timespan,
            startdatetime=inp.start_date_time,
            enddatetime=inp.end_date_time,
        )
        request_params = params.to_request_params()
        auth_headers   = self._doc_auth_headers()

        result: GDELTAPIResponse = await self._with_resilience(
            lambda: self._execute_with_cache_and_rate_limit(
                request_params, auth_headers,
                lambda: self._execute_doc_query(params, request_params, auth_headers),
            )
        )
        logger.info(f"Found {len(result.articles or [])} articles for: {inp.query}")
        return result

    async def search_images(self, inp: SearchImagesInput) -> GDELTAPIResponse:
        """Return news images matching the query (GDELT DOC 2.0 API)."""
        logger.info(f"Searching images: {inp.query}")

        image_type      = inp.image_type or "imagetag"
        formatted_query = f'{image_type}:"{inp.query}"'

        params = GDELTQueryParams(
            query=formatted_query,
            mode="ImageCollageInfo",
            format="JSON",
            maxrecords=inp.max_records or config.gdelt_default_max_records,
            timespan=inp.timespan or config.gdelt_default_timespan,
        )
        request_params = params.to_request_params()
        auth_headers   = self._doc_auth_headers()

        result: GDELTAPIResponse = await self._with_resilience(
            lambda: self._execute_with_cache_and_rate_limit(
                request_params, auth_headers,
                lambda: self._execute_doc_query(params, request_params, auth_headers),
            )
        )
        logger.info(f"Found {len(result.images or [])} images for: {inp.query}")
        return result

    async def search_media_events(
        self, inp: SearchMediaEventsInput
    ) -> GDELTMediaEventsResponse:
        """Return top media event clusters (GDELT Cloud API).

        Requires GDELT_API_KEY (gdelt_sk_*) on the Analyst or Professional plan.
        Data starts from January 2025, updated hourly.
        """
        if not config.gdelt_api_key:
            raise GDELTAuthError(
                "search_media_events requires a GDELT Cloud API key. "
                "Set the GDELT_API_KEY environment variable (format: gdelt_sk_...)."
            )

        logger.info(
            f"Searching media events: days={inp.days}, search={inp.search!r}, "
            f"category={inp.category}, scope={inp.scope}"
        )

        cloud_url      = f"{self._cloud_base_url}/api/v1/media-events"
        request_params = inp.to_request_params()
        auth_headers   = {"Authorization": f"Bearer {config.gdelt_api_key}"}

        result: GDELTMediaEventsResponse = await self._with_resilience(
            lambda: self._execute_with_cache_and_rate_limit(
                request_params, auth_headers,
                lambda: self._execute_cloud_query(cloud_url, request_params, auth_headers),
            )
        )
        count = len(result.clusters or [])
        logger.info(f"Found {count} media event cluster(s)")
        return result

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def cache_clear(self) -> int:
        """Evict all cached entries. Returns the count removed."""
        n = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cache cleared ({n} entries removed)")
        return n

    def cache_stats(self) -> dict[str, int]:
        """Return live / expired / total cache entry counts."""
        now  = time.monotonic()
        live = sum(1 for e in self._cache.values() if e.expires_at > now)
        return {"live": live, "expired": len(self._cache) - live, "total": len(self._cache)}

    # ------------------------------------------------------------------
    # Resilience — shared retry / backoff
    # ------------------------------------------------------------------

    async def _with_resilience(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Execute fn with exponential back-off retry.

        Non-retryable errors (quota exhaustion, auth failures, access denied)
        are re-raised immediately.
        """
        last_exc: RuntimeError | None = None
        for attempt in range(config.gdelt_max_retries):
            try:
                return await fn()
            except (GDELTQuotaExceededError, GDELTAuthError, GDELTAccessDeniedError, GDELTRateLimitError):
                raise   # not retryable
            except RuntimeError as exc:
                last_exc = exc
                if attempt >= config.gdelt_max_retries - 1:
                    break
                wait = self._retry_wait(exc, attempt)
                logger.warn(
                    f"Attempt {attempt + 1}/{config.gdelt_max_retries} failed, "
                    f"retrying in {wait:.0f}s: {exc}"
                )
                await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _retry_wait(self, exc: RuntimeError, attempt: int) -> float:
        """Seconds to wait before the next attempt.

        Standard exponential back-off: base_wait * 2^attempt (6, 12, 24 s …).
        429 rate-limit errors are non-retryable (GDELTRateLimitError) so they
        never reach this method.

        Jitter (py-gdelt pattern): a random fraction of the computed wait is
        added so that multiple concurrent clients don't all retry at the same
        instant (thundering-herd prevention).
        """
        base = config.gdelt_retry_base_wait * (2 ** attempt)
        # Add up to gdelt_retry_jitter * base seconds of random jitter
        return base + random.uniform(0, config.gdelt_retry_jitter * base)

    # ------------------------------------------------------------------
    # Cache + rate-limit wrapper (shared by all endpoints)
    # ------------------------------------------------------------------

    async def _execute_with_cache_and_rate_limit(
        self,
        request_params: dict[str, str],
        auth_headers:   dict[str, str],
        execute_fn: Callable[[], Awaitable[T]],
    ) -> T:
        """Check cache → enforce rate limit → execute → populate cache."""
        if config.gdelt_cache_ttl > 0:
            key    = self._cache_key(request_params)
            cached = self._cache_get(key)
            if cached is not None:
                logger.debug("Cache hit", {"key": key})
                return cached  # type: ignore[return-value]

        # Rate-limit gate
        loop    = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_request_time
        if elapsed < config.gdelt_rate_limit_interval:
            await asyncio.sleep(config.gdelt_rate_limit_interval - elapsed)

        result = await execute_fn()
        self._last_request_time = loop.time()   # advance only on success

        if config.gdelt_cache_ttl > 0:
            self._cache_set(key, result, request_params)  # type: ignore[possibly-undefined]

        return result

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, request_params: dict[str, str]) -> str:
        serialised = json.dumps(request_params, sort_keys=True)
        return hashlib.md5(serialised.encode()).hexdigest()

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            del self._cache[key]
            return None
        return entry.response

    def _cache_set(
        self,
        key: str,
        response: Any,
        request_params: dict[str, str] | None = None,
    ) -> None:
        """Store response with TTL.

        Tiered TTL (py-gdelt pattern): if the request targets a fixed
        historical window that ended more than gdelt_historical_threshold_days
        ago, the data can never change — use the much longer
        gdelt_historical_cache_ttl (default 24 h) instead of the standard TTL.
        """
        ttl = self._resolve_ttl(request_params)
        self._cache[key] = _CacheEntry(
            response=response,
            expires_at=time.monotonic() + ttl,
        )
        logger.debug("Cache set", {"key": key, "ttl": ttl})

    def _resolve_ttl(self, request_params: dict[str, str] | None) -> float:
        """Return the appropriate TTL for the given request.

        Historical detection: both ``startdatetime`` and ``enddatetime`` must
        be present and the end of the window must be older than
        ``gdelt_historical_threshold_days``.  All other requests use the
        standard ``gdelt_cache_ttl``.
        """
        hist_ttl = config.gdelt_historical_cache_ttl
        if (
            hist_ttl > 0
            and request_params
            and "startdatetime" in request_params
            and "enddatetime"   in request_params
        ):
            try:
                end_str = request_params["enddatetime"]  # YYYYMMDDHHMMSS
                end_dt  = datetime.strptime(end_str, "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc
                )
                age_days = (datetime.now(timezone.utc) - end_dt).days
                if age_days >= config.gdelt_historical_threshold_days:
                    return hist_ttl
            except (ValueError, OverflowError):
                pass
        return config.gdelt_cache_ttl

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _doc_auth_headers(self) -> dict[str, str]:
        """Bearer header for DOC 2.0 calls when a key is configured."""
        return {"Authorization": f"Bearer {config.gdelt_api_key}"} if config.gdelt_api_key else {}

    # ------------------------------------------------------------------
    # HTTP error handling (shared)
    # ------------------------------------------------------------------

    def _handle_http_error(self, exc: httpx.HTTPStatusError) -> None:
        """Raise the appropriate typed exception for a non-2xx response."""
        status = exc.response.status_code

        error_code = ""
        try:
            error_code = exc.response.json().get("code", "")
        except Exception:
            pass

        if status == 429:
            retry_after = exc.response.headers.get("Retry-After", "")
            if error_code == "QUOTA_EXCEEDED":
                msg = "GDELT API monthly quota exceeded (429 QUOTA_EXCEEDED)"
                logger.error(msg)
                raise GDELTQuotaExceededError(msg) from exc
            hint     = f" — wait {retry_after}s before retrying" if retry_after else ""
            code_tag = f" [{error_code}]" if error_code else ""
            msg = f"GDELT API rate limit (429{code_tag}){hint}"
            logger.error(msg)
            raise GDELTRateLimitError(msg) from exc

        if status == 401:
            msg = f"GDELT API authentication failed (401 {error_code or 'UNAUTHORIZED'})"
            logger.error(msg)
            raise GDELTAuthError(msg) from exc

        if status == 403:
            msg = f"GDELT API access denied (403 {error_code or 'FORBIDDEN'})"
            logger.error(msg)
            raise GDELTAccessDeniedError(msg) from exc

        msg = f"GDELT API HTTP error {status}: {exc.response.text[:200]}"
        logger.error(msg)
        raise RuntimeError(msg) from exc

    # ------------------------------------------------------------------
    # Low-level HTTP execution — DOC 2.0 API
    # ------------------------------------------------------------------

    async def _execute_doc_query(
        self,
        params:        GDELTQueryParams,
        request_params: dict[str, str],
        auth_headers:   dict[str, str],
    ) -> GDELTAPIResponse:
        logger.debug("GDELT DOC request", {"url": self._base_url, "params": request_params})

        try:
            response = await self._client.get(
                self._base_url, params=request_params, headers=auth_headers
            )
            response.raise_for_status()

            if params.format == "JSON":
                data = response.json()
                logger.debug("GDELT DOC response", {"status": response.status_code, "bytes": len(response.content)})
                return GDELTAPIResponse.model_validate(data)

            return GDELTAPIResponse()

        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc)

        except httpx.RequestError as exc:
            msg = f"GDELT API request failed ({type(exc).__name__}): {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        except ValueError as exc:
            if not response.text.strip():
                logger.debug("GDELT DOC returned empty body — treating as no results")
                return GDELTAPIResponse()
            msg = f"GDELT DOC response is not valid JSON: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    # ------------------------------------------------------------------
    # Low-level HTTP execution — GDELT Cloud API
    # ------------------------------------------------------------------

    async def _execute_cloud_query(
        self,
        url:            str,
        request_params: dict[str, str],
        auth_headers:   dict[str, str],
    ) -> GDELTMediaEventsResponse:
        logger.debug("GDELT Cloud request", {"url": url, "params": request_params})

        try:
            response = await self._client.get(url, params=request_params, headers=auth_headers)
            response.raise_for_status()

            data = response.json()
            logger.debug("GDELT Cloud response", {"status": response.status_code, "bytes": len(response.content)})
            return GDELTMediaEventsResponse.model_validate(data)

        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc)

        except httpx.RequestError as exc:
            msg = f"GDELT Cloud request failed ({type(exc).__name__}): {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        except ValueError as exc:
            if not response.text.strip():
                logger.debug("GDELT Cloud returned empty body — treating as no results")
                return GDELTMediaEventsResponse()
            msg = f"GDELT Cloud response is not valid JSON: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# Singleton instance used by the server
gdelt_client = GDELTClient()
