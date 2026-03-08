#!/usr/bin/env python3
"""GDELT MCP Server — Python implementation.

Exposes two MCP tools:
  • search_articles  – search GDELT's global news database
  • search_images    – search GDELT's Visual Knowledge Graph (VGKG)

Transport: stdio  (compatible with Claude Desktop and any MCP client)
"""

from __future__ import annotations

import json
import signal
import sys

from mcp.server.fastmcp import FastMCP

from .logger import logger
from .services import gdelt_client
from .types import SearchArticlesInput, SearchImagesInput

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
) -> str:
    """Search GDELT news articles.

    Args:
        query: Search query (keywords, quoted phrases, OR/AND operators).
        max_records: Maximum articles to return (1–250, default 50).
        timespan: Time period, e.g. "1month", "7d", "24h" (default "1month").
        sort: Sort order — DateDesc | DateAsc | ToneAsc | ToneDesc | HybridRel.
        start_date_time: Start date in YYYYMMDDHHMMSS format.
        end_date_time: End date in YYYYMMDDHHMMSS format.
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
