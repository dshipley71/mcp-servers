#!/usr/bin/env python3
"""GDELT MCP Server — Python implementation.

Exposes three MCP tools:
  • search_articles      – search GDELT's global news database
  • search_images        – search GDELT's Visual Knowledge Graph (VGKG)
  • search_media_events  – search GDELT Cloud top media event clusters (requires API key)

Transport: stdio  (compatible with Claude Desktop and any MCP client)
"""

from __future__ import annotations

import json
import signal
import sys

from mcp.server.fastmcp import FastMCP

from .logger import logger
from .services import gdelt_client
from .types import SearchArticlesInput, SearchImagesInput, SearchMediaEventsInput

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("mcp-gdelt")


# ---------------------------------------------------------------------------
# Tool: search_articles
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search GDELT's global news database for articles across 65 languages. "
        "Supports keyword/phrase searches, Boolean operators (OR, AND), and searches "
        "back 3 months. Default returns 50 most recent articles from the past month."
    )
)
async def search_articles(
    query: str,
    max_records: int | None = None,
    timespan: str | None = None,
    sort: str | None = None,
    start_date_time: str | None = None,
    end_date_time: str | None = None,
    deduplicate: bool = True,
) -> str:
    """Search GDELT news articles.

    Args:
        query: Search query (keywords, quoted phrases, OR/AND operators).
        max_records: Maximum articles to return (1–250, default 50).
        timespan: Time period, e.g. "1month", "7d", "24h" (default "1month").
        sort: Sort order — DateDesc | DateAsc | ToneAsc | ToneDesc | HybridRel.
        start_date_time: Start date in YYYYMMDDHHMMSS format.
        end_date_time: End date in YYYYMMDDHHMMSS format.
        deduplicate: Remove duplicate URLs from results (default True).
    """
    try:
        logger.info(f"Tool: search_articles — query: {query}")

        inp = SearchArticlesInput(
            query=query,
            max_records=max_records,
            timespan=timespan,
            sort=sort,  # type: ignore[arg-type]
            start_date_time=start_date_time,
            end_date_time=end_date_time,
            deduplicate=deduplicate,
        )

        result = await gdelt_client.search_articles(inp)
        count = len(result.articles or [])
        logger.info(f"Tool: search_articles — success: {count} articles found")

        return json.dumps(result.model_dump(exclude_none=True), indent=2)

    except Exception as exc:
        logger.error(f"Tool: search_articles — failed: {exc}")
        raise ValueError(f"Failed to search articles: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool: search_images
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search GDELT's Visual Knowledge Graph (VGKG) for news images. "
        "Can search by visual content (what's depicted), captions/context, "
        "or OCR/metadata. Searches back 3 months of global news imagery."
    )
)
async def search_images(
    query: str,
    max_records: int | None = None,
    timespan: str | None = None,
    image_type: str | None = None,
) -> str:
    """Search GDELT news images.

    Args:
        query: Search term, e.g. "fire", "protest", "flood".
        max_records: Maximum images to return (1–250, default 50).
        timespan: Time period, e.g. "1month", "7d", "24h" (default "1month").
        image_type: imagetag (AI visual content) | imagewebtag (caption/context)
                    | imageocrmeta (OCR + metadata). Default: imagetag.
    """
    try:
        logger.info(f"Tool: search_images — query: {query}")

        inp = SearchImagesInput(
            query=query,
            max_records=max_records,
            timespan=timespan,
            image_type=image_type,  # type: ignore[arg-type]
        )

        result = await gdelt_client.search_images(inp)
        count = len(result.images or [])
        logger.info(f"Tool: search_images — success: {count} images found")

        return json.dumps(result.model_dump(exclude_none=True), indent=2)

    except Exception as exc:
        logger.error(f"Tool: search_images — failed: {exc}")
        raise ValueError(f"Failed to search images: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool: search_media_events
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Search GDELT Cloud for top media event clusters using CAMEO-coded geopolitical events. "
        "Requires a GDELT Cloud API key (set GDELT_API_KEY env var). "
        "Supports semantic search, category/scope filtering, actor/location filters, "
        "Goldstein scale and tone range filters, and CAMEO event type codes. "
        "Data starts from January 2025, updated hourly."
    )
)
async def search_media_events(
    days: int | None = None,
    date: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    detail: str | None = None,
    search: str | None = None,
    category: str | None = None,
    scope: str | None = None,
    actor_country: str | None = None,
    event_type: str | None = None,
    country: str | None = None,
    location: str | None = None,
    language: str | None = None,
    domain: str | None = None,
    goldstein_min: float | None = None,
    goldstein_max: float | None = None,
    tone_min: float | None = None,
    tone_max: float | None = None,
    quad_class: int | None = None,
) -> str:
    """Search GDELT Cloud top media event clusters.

    Args:
        days: Window size in days ending on `date` (1–30, default 1).
        date: Anchor/end date of the time window (YYYY-MM-DD, default today UTC).
        limit: Number of clusters to return (1–50, default 10).
        offset: Clusters to skip for pagination (default 0).
        detail: Response verbosity — summary | standard | full (default full).
        search: Natural-language semantic search query.
        category: Topic category filter (comma-separated). Valid: conflict_security,
                  politics_governance, crime_justice, economy_business, science_health,
                  disaster_emergency, society_culture, technology.
        scope: Geographic scope filter — local | national | global.
        actor_country: CAMEO ISO-3 country code for actor1 or actor2 (e.g. USA, GBR).
        event_type: CAMEO event root code (e.g. '14'=Protest, '18'=Assault, '19'=Fight).
        country: Friendly country filter — full name, ISO-3/CAMEO-3, or FIPS-2 code.
        location: Raw FIPS 10-4 two-letter country prefix (e.g. 'US', 'GM').
        language: Language filter — full name ('English') or ISO-639-1 code ('en').
        domain: Filter to clusters with at least one article from this domain.
        goldstein_min: Minimum Goldstein scale value (-10 to +10).
        goldstein_max: Maximum Goldstein scale value (-10 to +10).
        tone_min: Minimum average tone value.
        tone_max: Maximum average tone value.
        quad_class: Quad class — 1=Verbal Cooperation, 2=Material Cooperation,
                    3=Verbal Conflict, 4=Material Conflict.
    """
    try:
        logger.info(f"Tool: search_media_events — search={search!r}, days={days}, category={category}")

        inp = SearchMediaEventsInput(
            days=days,
            date=date,
            limit=limit,
            offset=offset,
            detail=detail,  # type: ignore[arg-type]
            search=search,
            category=category,
            scope=scope,  # type: ignore[arg-type]
            actor_country=actor_country,
            event_type=event_type,
            country=country,
            location=location,
            language=language,
            domain=domain,
            goldstein_min=goldstein_min,
            goldstein_max=goldstein_max,
            tone_min=tone_min,
            tone_max=tone_max,
            quad_class=quad_class,  # type: ignore[arg-type]
        )

        result = await gdelt_client.search_media_events(inp)
        count = len(result.clusters or [])
        logger.info(f"Tool: search_media_events — success: {count} cluster(s) found")

        return json.dumps(result.model_dump(exclude_none=True), indent=2)

    except Exception as exc:
        logger.error(f"Tool: search_media_events — failed: {exc}")
        raise ValueError(f"Failed to search media events: {exc}") from exc


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
    logger.info("Shutting down MCP-GDELT server…")
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Starting MCP-GDELT server (stdio transport)…")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
