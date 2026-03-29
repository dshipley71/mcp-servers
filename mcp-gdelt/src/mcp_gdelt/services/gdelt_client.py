"""Async GDELT DOC 2.0 API client backed by httpx."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass

import httpx

from ..config import config
from ..logger import logger
from ..types import (
    GDELTAPIResponse,
    GDELTQueryParams,
    SearchArticlesInput,
    SearchImagesInput,
)


class GDELTQuotaExceededError(RuntimeError):
    """Raised when the monthly API quota is exhausted (HTTP 429 QUOTA_EXCEEDED).

    Unlike a transient rate-limit, a quota exhaustion cannot be resolved by
    waiting — retrying would waste the last remaining headroom on other calls.
    """


@dataclass
class _CacheEntry:
    response: GDELTAPIResponse
    expires_at: float   # monotonic seconds


class GDELTClient:
    """Async wrapper around the GDELT DOC 2.0 API with rate limiting, retry, and caching."""

    def __init__(self) -> None:
        self._base_url = config.gdelt_api_base_url
        self._client = httpx.AsyncClient(
            timeout=config.gdelt_api_timeout,
            headers={"User-Agent": config.gdelt_user_agent},
            follow_redirects=True,   # GDELT redirects; httpx default is False
        )
        self._last_request_time: float = 0.0
        self._cache: dict[str, _CacheEntry] = {}
        logger.debug(
            "GDELTClient initialised",
            {
                "base_url": self._base_url,
                "timeout": config.gdelt_api_timeout,
                "cache_ttl": config.gdelt_cache_ttl,
                "rate_limit_interval": config.gdelt_rate_limit_interval,
            },
        )

    # ------------------------------------------------------------------
    # Public tool methods
    # ------------------------------------------------------------------

    async def search_articles(self, inp: SearchArticlesInput) -> GDELTAPIResponse:
        """Return a list of news articles matching the query."""
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

        result = await self._with_retry(params)
        logger.info(f"Found {len(result.articles or [])} articles for: {inp.query}")
        return result

    async def search_images(self, inp: SearchImagesInput) -> GDELTAPIResponse:
        """Return a list of news images matching the query."""
        logger.info(f"Searching images: {inp.query}")

        image_type = inp.image_type or "imagetag"
        formatted_query = f'{image_type}:"{inp.query}"'

        params = GDELTQueryParams(
            query=formatted_query,
            mode="ImageCollageInfo",
            format="JSON",
            maxrecords=inp.max_records or config.gdelt_default_max_records,
            timespan=inp.timespan or config.gdelt_default_timespan,
        )

        result = await self._with_retry(params)
        logger.info(f"Found {len(result.images or [])} images for: {inp.query}")
        return result

    def cache_clear(self) -> int:
        """Evict all cached entries and return the count removed."""
        n = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cache cleared ({n} entries removed)")
        return n

    def cache_stats(self) -> dict[str, int]:
        """Return counts of live vs expired cache entries."""
        now = time.monotonic()
        live = sum(1 for e in self._cache.values() if e.expires_at > now)
        return {"live": live, "expired": len(self._cache) - live, "total": len(self._cache)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _with_retry(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        """Execute a query with exponential back-off retry.

        GDELTQuotaExceededError (monthly quota) is re-raised immediately
        without retrying — the quota cannot be restored by waiting.
        """
        last_exc: RuntimeError | None = None
        for attempt in range(config.gdelt_max_retries):
            try:
                return await self._cached_execute(params)
            except GDELTQuotaExceededError:
                raise  # monthly quota — retrying won't help
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
        """Return seconds to wait before the next attempt.

        RATE_LIMITED errors use Retry-After when available, then exponential
        back-off.  Other transient errors use the standard base_wait schedule.
        """
        msg = str(exc)
        if "RATE_LIMITED" in msg or "rate limit" in msg.lower():
            m = re.search(r"Retry-After:\s*(\d+)", msg)
            if m:
                return float(m.group(1)) + 2
            # Exponential: 60 s, 120 s, 240 s … capped at 5 min
            return min(config.gdelt_retry_rate_limit_wait * (2 ** attempt), 300.0)
        return config.gdelt_retry_base_wait * (2 ** attempt)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, request_params: dict[str, str]) -> str:
        serialised = json.dumps(request_params, sort_keys=True)
        return hashlib.md5(serialised.encode()).hexdigest()

    def _cache_get(self, key: str) -> GDELTAPIResponse | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            del self._cache[key]
            return None
        return entry.response

    def _cache_set(self, key: str, response: GDELTAPIResponse) -> None:
        self._cache[key] = _CacheEntry(
            response=response,
            expires_at=time.monotonic() + config.gdelt_cache_ttl,
        )

    # ------------------------------------------------------------------
    # Rate-limited + cached execution
    # ------------------------------------------------------------------

    async def _cached_execute(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        """Return a cached result when available, otherwise hit the API."""
        request_params = params.to_request_params()
        # Bearer token is sent as a header; exclude it from the cache key so
        # the key reflects query intent only (same query == same cached result
        # regardless of which credential is active).
        auth_headers: dict[str, str] = {}
        if config.gdelt_api_key:
            auth_headers["Authorization"] = f"Bearer {config.gdelt_api_key}"

        if config.gdelt_cache_ttl > 0:
            key = self._cache_key(request_params)
            cached = self._cache_get(key)
            if cached is not None:
                logger.debug("Cache hit", {"key": key})
                return cached

        result = await self._rate_limited_execute(params, request_params, auth_headers)

        if config.gdelt_cache_ttl > 0:
            self._cache_set(key, result)  # type: ignore[possibly-undefined]

        return result

    async def _rate_limited_execute(
        self,
        params: GDELTQueryParams,
        request_params: dict[str, str],
        auth_headers: dict[str, str],
    ) -> GDELTAPIResponse:
        """Enforce the per-request rate limit, then execute the query."""
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_request_time
        if elapsed < config.gdelt_rate_limit_interval:
            await asyncio.sleep(config.gdelt_rate_limit_interval - elapsed)
        result = await self._execute_query(params, request_params, auth_headers)
        self._last_request_time = loop.time()  # advance only after a completed call
        return result

    async def _execute_query(
        self,
        params: GDELTQueryParams,
        request_params: dict[str, str],
        auth_headers: dict[str, str],
    ) -> GDELTAPIResponse:
        logger.debug("GDELT API request", {"url": self._base_url, "params": request_params})

        try:
            response = await self._client.get(
                self._base_url, params=request_params, headers=auth_headers
            )
            response.raise_for_status()

            if params.format == "JSON":
                data = response.json()
                logger.debug(
                    "GDELT API response",
                    {"status": response.status_code, "bytes": len(response.content)},
                )
                return GDELTAPIResponse.model_validate(data)

            return GDELTAPIResponse()

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                # Parse the machine-readable code from the response body.
                # RATE_LIMITED  → per-minute limit; Retry-After header present
                # QUOTA_EXCEEDED → monthly quota exhausted; no Retry-After
                error_code = ""
                try:
                    error_code = exc.response.json().get("code", "")
                except Exception:
                    pass

                retry_after = exc.response.headers.get("Retry-After", "")

                if error_code == "QUOTA_EXCEEDED":
                    msg = "GDELT API monthly quota exceeded (429 QUOTA_EXCEEDED)"
                    logger.error(msg)
                    raise GDELTQuotaExceededError(msg) from exc

                hint = f" — Retry-After: {retry_after}s" if retry_after else ""
                code_tag = f" [{error_code}]" if error_code else ""
                msg = f"GDELT API rate limit (429{code_tag}){hint}"
            else:
                msg = f"GDELT API HTTP error {status}: {exc.response.text[:200]}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        except httpx.RequestError as exc:
            msg = f"GDELT API request failed: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        except ValueError as exc:
            # json.JSONDecodeError (subclass of ValueError) is raised when
            # the response body is empty or not valid JSON — e.g. when httpx
            # receives a redirect without follow_redirects=True, or when GDELT
            # returns a null/empty body for a no-results query.
            # Use response.text (httpx-decoded string) rather than raw bytes so
            # that a UTF-8 BOM prefix or other encoding preamble is stripped
            # before the emptiness check.
            if not response.text.strip():
                logger.debug("GDELT API returned empty body — treating as no results")
                return GDELTAPIResponse()
            msg = f"GDELT API response is not valid JSON: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# Singleton instance used by the server
gdelt_client = GDELTClient()
