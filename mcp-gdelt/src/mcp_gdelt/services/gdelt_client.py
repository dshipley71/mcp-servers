"""Async GDELT DOC 2.0 API client backed by httpx."""

from __future__ import annotations

import asyncio
import re

import httpx

from ..config import config
from ..logger import logger
from ..types import (
    GDELTAPIResponse,
    GDELTQueryParams,
    SearchArticlesInput,
    SearchImagesInput,
)


class GDELTClient:
    """Async wrapper around the GDELT DOC 2.0 API with rate limiting and retry."""

    def __init__(self) -> None:
        self._base_url = config.gdelt_api_base_url
        self._client = httpx.AsyncClient(
            timeout=config.gdelt_api_timeout,
            headers={"User-Agent": config.gdelt_user_agent},
            follow_redirects=True,   # GDELT redirects; httpx default is False
        )
        self._last_request_time: float = 0.0
        logger.debug(
            "GDELTClient initialised",
            {"base_url": self._base_url, "timeout": config.gdelt_api_timeout},
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _with_retry(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        """Execute a query with exponential back-off retry."""
        last_exc: RuntimeError | None = None
        for attempt in range(config.gdelt_max_retries):
            try:
                return await self._rate_limited_execute(params)
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
        """Return seconds to wait before the next attempt."""
        msg = str(exc)
        if "429" in msg or "rate limit" in msg.lower():
            m = re.search(r"Retry-After:\s*(\d+)", msg)
            return float(m.group(1)) + 2 if m else config.gdelt_retry_rate_limit_wait
        return config.gdelt_retry_base_wait * (2 ** attempt)

    async def _rate_limited_execute(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        """Enforce the per-request rate limit, then execute the query."""
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_request_time
        if elapsed < config.gdelt_rate_limit_interval:
            await asyncio.sleep(config.gdelt_rate_limit_interval - elapsed)
        result = await self._execute_query(params)
        self._last_request_time = loop.time()  # advance only after a completed call
        return result

    async def _execute_query(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        request_params = params.to_request_params()
        if config.gdelt_api_key:
            request_params["key"] = config.gdelt_api_key
        logger.debug("GDELT API request", {"url": self._base_url, "params": request_params})

        try:
            response = await self._client.get(self._base_url, params=request_params)
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
                retry_after = exc.response.headers.get("Retry-After", "")
                hint = f" — Retry-After: {retry_after}s" if retry_after else ""
                msg = f"GDELT API rate limit (429){hint}"
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
