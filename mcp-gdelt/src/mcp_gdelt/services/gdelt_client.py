"""Async GDELT DOC 2.0 API client backed by httpx."""

from __future__ import annotations

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
    """Thin async wrapper around the GDELT DOC 2.0 API."""

    def __init__(self) -> None:
        self._base_url = config.gdelt_api_base_url
        self._client = httpx.AsyncClient(
            timeout=config.gdelt_api_timeout,
            headers={"User-Agent": config.gdelt_user_agent},
            follow_redirects=True,   # GDELT redirects; httpx default is False
        )
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

        result = await self._execute_query(params)
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

        result = await self._execute_query(params)
        logger.info(f"Found {len(result.images or [])} images for: {inp.query}")
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_query(self, params: GDELTQueryParams) -> GDELTAPIResponse:
        request_params = params.to_request_params()
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
            msg = f"GDELT API HTTP error {exc.response.status_code}: {exc.response.text[:200]}"
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
            if not response.content.strip():
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
