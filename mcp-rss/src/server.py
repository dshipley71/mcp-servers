#!/usr/bin/env python3
"""MCP-RSS server — Python rewrite of the original TypeScript implementation."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

from .config import config
from .logger import logger
from .services.cache import feed_cache
from .services.rss_reader import rss_reader
from .types import FeedItem, FeedResult, MultiFeedResult
from .utils.date import now_ms

# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------

mcp = FastMCP("mcp-rss")


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses → plain dicts (JSON-serialisable)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    return obj


def _dumps(obj: Any) -> str:
    return json.dumps(_to_dict(obj), indent=2)


# ---------------------------------------------------------------------------
# Tool 1: fetch_rss_feed
# ---------------------------------------------------------------------------

@mcp.tool()
async def fetch_rss_feed(
    url: str,
    use_description_as_content: Optional[str] = None,
) -> str:
    """Fetch and parse an RSS feed, returning structured data with feed info and items.

    Args:
        url: The URL of the RSS feed to fetch.
        use_description_as_content: If 'true', use description field as content
            instead of the content field.
    """
    logger.info(f"Fetching RSS feed: {url}")

    # Cache hit
    cached = feed_cache.get(url)
    if cached:
        logger.debug(f"Returning cached feed: {url}")
        return _dumps(cached)

    cache_meta = feed_cache.get_metadata(url)

    try:
        result = await rss_reader.fetch_feed(
            url,
            use_description_as_content=(use_description_as_content == "true"),
            etag=cache_meta["etag"] if cache_meta else None,
            last_modified=cache_meta["last_modified"] if cache_meta else None,
        )
    except RuntimeError as exc:
        if "NOT_MODIFIED" in str(exc) and feed_cache.has(url):
            cached = feed_cache.get(url)
            if cached:
                logger.debug(f"Feed not modified, returning cache: {url}")
                return _dumps(cached)
        logger.error(f"Failed to fetch RSS feed {url}: {exc}")
        raise ValueError(f"Failed to fetch RSS feed: {exc}") from exc

    feed_cache.set(url, result)
    logger.info(f"Successfully fetched feed: {url}, {len(result.items)} items")
    return _dumps(result)


# ---------------------------------------------------------------------------
# Tool 2: fetch_multiple_feeds
# ---------------------------------------------------------------------------

@mcp.tool()
async def fetch_multiple_feeds(
    urls: list[str],
    parallel: Optional[str] = "true",
) -> str:
    """Batch-fetch multiple RSS feeds with per-feed success/error status.

    Args:
        urls: List of RSS feed URLs to fetch.
        parallel: If 'true' (default), fetch feeds in parallel; otherwise sequential.
    """
    logger.info(f"Fetching {len(urls)} feeds (parallel: {parallel})")

    async def _fetch_one(url: str) -> MultiFeedResult:
        try:
            cached = feed_cache.get(url)
            if cached:
                return MultiFeedResult(url=url, success=True, data=cached)
            result = await rss_reader.fetch_feed(url)
            feed_cache.set(url, result)
            return MultiFeedResult(url=url, success=True, data=result)
        except Exception as exc:
            logger.error(f"Failed to fetch {url}: {exc}")
            from .types import FeedError
            return MultiFeedResult(
                url=url,
                success=False,
                error=FeedError(url=url, error=str(exc), timestamp=now_ms()),
            )

    results: list[MultiFeedResult]

    if parallel != "false":
        # Parallel with concurrency cap
        chunks = [
            urls[i: i + config.rss_max_concurrent_fetches]
            for i in range(0, len(urls), config.rss_max_concurrent_fetches)
        ]
        results = []
        for chunk in chunks:
            chunk_results = await asyncio.gather(*[_fetch_one(u) for u in chunk])
            results.extend(chunk_results)
    else:
        results = []
        for url in urls:
            results.append(await _fetch_one(url))

    success_count = sum(1 for r in results if r.success)
    logger.info(f"Fetched {success_count}/{len(urls)} feeds successfully")

    return json.dumps(
        {
            "total": len(urls),
            "successful": success_count,
            "failed": len(urls) - success_count,
            "results": [_to_dict(r) for r in results],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 3: monitor_feed_updates
# ---------------------------------------------------------------------------

@mcp.tool()
async def monitor_feed_updates(
    url: str,
    since: Union[int, str],
) -> str:
    """Check for new items in a feed since a specific time or last check.

    Args:
        url: The RSS feed URL to monitor.
        since: Epoch milliseconds timestamp, or the literal string 'last'
               to compare against the last cached fetch time.
    """
    logger.info(f"Monitoring updates for: {url} since {since}")

    current_feed = await rss_reader.fetch_feed(url)

    if since == "last":
        cached = feed_cache.get(url)
        since_ts = cached.fetched_at if cached else 0
    else:
        try:
            since_ts = int(since)
        except (ValueError, TypeError):
            raise ValueError("'since' must be an integer timestamp or 'last'")

    new_items = [
        item
        for item in current_feed.items
        if (item.published or item.updated or 0) > since_ts
    ]

    feed_cache.set(url, current_feed)

    logger.info(
        f"Found {len(new_items)} new items since "
        f"{datetime.fromtimestamp(since_ts / 1000, tz=timezone.utc).isoformat()}"
    )

    checked_at = current_feed.fetched_at
    return json.dumps(
        {
            "feedUrl": url,
            "feedTitle": current_feed.info.title,
            "since": since_ts,
            "sinceISO": datetime.fromtimestamp(
                since_ts / 1000, tz=timezone.utc
            ).isoformat(),
            "checkedAt": checked_at,
            "checkedAtISO": datetime.fromtimestamp(
                checked_at / 1000, tz=timezone.utc
            ).isoformat(),
            "newItemsCount": len(new_items),
            "totalItemsCount": len(current_feed.items),
            "newItems": [_to_dict(i) for i in new_items],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 4: search_feed_items
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_feed_items(
    feeds: list[str],
    query: str,
    search_in: Optional[str] = "all",
) -> str:
    """Search for content across one or more RSS feeds.

    Args:
        feeds: List of RSS feed URLs to search.
        query: Search query string (case-insensitive).
        search_in: Which fields to search: 'title', 'description', 'content',
                   or 'all' (default).
    """
    if search_in not in ("title", "description", "content", "all"):
        search_in = "all"

    logger.info(f"Searching {len(feeds)} feeds for: \"{query}\"")

    search_results = []
    q = query.lower()

    for feed_url in feeds:
        try:
            feed: FeedResult | None = feed_cache.get(feed_url)
            if feed is None:
                feed = await rss_reader.fetch_feed(feed_url)
                feed_cache.set(feed_url, feed)

            for item in feed.items:
                matches: list[str] = []
                if search_in in ("all", "title") and item.title and q in item.title.lower():
                    matches.append("title")
                if search_in in ("all", "description") and item.description and q in item.description.lower():
                    matches.append("description")
                if search_in in ("all", "content") and item.content and q in item.content.lower():
                    matches.append("content")
                if matches:
                    search_results.append(
                        {
                            "feedUrl": feed_url,
                            "feedTitle": feed.info.title,
                            "item": _to_dict(item),
                            "matches": matches,
                        }
                    )
        except Exception as exc:
            logger.error(f"Failed to search feed {feed_url}: {exc}")

    logger.info(f"Found {len(search_results)} matching items")

    return json.dumps(
        {
            "query": query,
            "searchIn": search_in,
            "feedsSearched": len(feeds),
            "totalMatches": len(search_results),
            "results": search_results,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 5: extract_feed_content
# ---------------------------------------------------------------------------

@mcp.tool()
async def extract_feed_content(
    url: str,
    format: Optional[str] = "text",
    include_metadata: Optional[str] = "false",
) -> str:
    """Extract and format feed content for different use cases.

    Args:
        url: The RSS feed URL to extract content from.
        format: Output format — 'markdown', 'text' (default), 'html', or 'json'.
        include_metadata: If 'true', include item metadata (date, author, etc).
    """
    if format not in ("markdown", "text", "html", "json"):
        format = "text"

    logger.info(f"Extracting content from: {url} (format: {format})")

    feed: FeedResult | None = feed_cache.get(url)
    if feed is None:
        feed = await rss_reader.fetch_feed(url)
        feed_cache.set(url, feed)

    with_meta = include_metadata == "true"

    def _format_item(item: FeedItem):
        content = item.content or item.description or ""
        metadata = {
            "title": item.title,
            "author": item.author,
            "published": (
                datetime.fromtimestamp(item.published / 1000, tz=timezone.utc).isoformat()
                if item.published
                else None
            ),
            "url": item.url,
            "categories": item.categories,
        }

        if format == "json":
            return {**metadata, "content": content} if with_meta else {"content": content}

        meta_lines = []
        if with_meta:
            if item.title:
                meta_lines.append(f"Title: {item.title}")
            if item.author:
                meta_lines.append(f"Author: {item.author}")
            if item.published:
                meta_lines.append(
                    f"Published: {datetime.fromtimestamp(item.published / 1000, tz=timezone.utc).isoformat()}"
                )
            if item.url:
                meta_lines.append(f"URL: {item.url}")
            if item.categories:
                meta_lines.append(f"Categories: {', '.join(item.categories)}")
        meta_text = "\n".join(meta_lines)

        if format == "markdown":
            parts = []
            if item.title:
                parts.append(f"# {item.title}")
            if meta_text:
                parts.append(meta_text)
            if content:
                parts.append(content)
            if item.url:
                parts.append(f"\n[Read more]({item.url})")
            return "\n\n".join(parts)

        if format == "html":
            html_parts = []
            if item.title:
                html_parts.append(f"<h1>{item.title}</h1>")
            if meta_text:
                html_parts.append(
                    f'<div class="metadata">{meta_text.replace(chr(10), "<br>")}</div>'
                )
            if content:
                html_parts.append(f'<div class="content">{content}</div>')
            if item.url:
                html_parts.append(f'<p><a href="{item.url}">Read more</a></p>')
            return "\n".join(html_parts)

        # Plain text (default)
        text_parts = []
        if item.title:
            text_parts.append(item.title)
        if meta_text:
            text_parts.append(meta_text)
        if content:
            text_parts.append(content)
        return "\n\n".join(text_parts)

    formatted = [_format_item(item) for item in feed.items]
    now = now_ms()

    output = {
        "feedTitle": feed.info.title,
        "feedUrl": url,
        "itemCount": len(feed.items),
        "format": format,
        "extractedAt": now,
        "extractedAtISO": datetime.fromtimestamp(now / 1000, tz=timezone.utc).isoformat(),
        "content": formatted,
    }

    logger.info(f"Extracted content from {len(feed.items)} items")
    return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# Tool 6: get_feed_headlines
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_feed_headlines(
    url: str,
    format: Optional[str] = "json",
) -> str:
    """Get a list of headlines from a feed including title, summary, and URL.

    Args:
        url: The RSS feed URL to get headlines from.
        format: Output format — 'markdown', 'text', 'html', or 'json' (default).
    """
    if format not in ("markdown", "text", "html", "json"):
        format = "json"

    logger.info(f"Getting headlines from: {url}")

    feed: FeedResult | None = feed_cache.get(url)
    if feed is None:
        feed = await rss_reader.fetch_feed(url)
        feed_cache.set(url, feed)

    def _format_headline(item: FeedItem):
        summary = item.description or item.content
        if format == "markdown":
            return f"### [{item.title}]({item.url})\n{summary}"
        if format == "html":
            return f'<h3><a href="{item.url}">{item.title}</a></h3><p>{summary}</p>'
        if format == "text":
            return f"{item.title}\n{summary}\n{item.url}"
        # json (default)
        return {
            "title": item.title,
            "summary": summary,
            "url": item.url,
            "published": item.published,
            "author": item.author,
        }

    headlines = [_format_headline(item) for item in feed.items]
    logger.info(f"Got {len(headlines)} headlines from {url}")

    return json.dumps(
        {
            "feedTitle": feed.info.title,
            "feedUrl": url,
            "itemCount": len(feed.items),
            "format": format,
            "headlines": headlines,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Resource 1: rss://cache/{feedUrl}
# ---------------------------------------------------------------------------

@mcp.resource("rss://cache/{feed_url}")
async def rss_cache_resource(feed_url: str) -> str:
    """Access cached feed data to avoid redundant fetches.

    URI: rss://cache/{feed_url}
    """
    cached = feed_cache.get(feed_url)
    if not cached:
        return json.dumps(
            {"error": "Feed not found in cache", "feedUrl": feed_url}, indent=2
        )
    return json.dumps(
        {
            "cached": True,
            "feedUrl": feed_url,
            "cachedAt": cached.fetched_at,
            "data": _to_dict(cached),
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Resource 2: rss://opml/export
# ---------------------------------------------------------------------------

def _escape_xml(value: str) -> str:
    if not value:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


@mcp.resource("rss://opml/export")
async def opml_export_resource() -> str:
    """Export all monitored feeds as OPML format.

    URI: rss://opml/export
    """
    stats = feed_cache.get_stats()
    opml_feeds = []
    for url in stats["urls"]:
        cached = feed_cache.get(url)
        if cached:
            opml_feeds.append(
                {
                    "url": url,
                    "title": cached.info.title,
                    "html_url": cached.info.url,
                }
            )

    outline_entries = "\n".join(
        f'      <outline type="rss" text="{_escape_xml(f["title"] or f["url"])}" '
        f'title="{_escape_xml(f["title"] or f["url"])}" '
        f'xmlUrl="{_escape_xml(f["url"])}" '
        f'htmlUrl="{_escape_xml(f["html_url"] or "")}" />'
        for f in opml_feeds
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        "  <head>\n"
        "    <title>MCP-RSS Feed Subscriptions</title>\n"
        f"    <dateCreated>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')}</dateCreated>\n"
        "    <ownerName>MCP-RSS Server</ownerName>\n"
        "  </head>\n"
        "  <body>\n"
        '    <outline text="RSS Feeds" title="RSS Feeds">\n'
        f"{outline_entries}\n"
        "    </outline>\n"
        "  </body>\n"
        "</opml>"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    feed_cache.start()
    logger.info("MCP-RSS server starting...")
    try:
        await mcp.run_stdio_async()
    finally:
        feed_cache.destroy()
        logger.info("MCP-RSS server shut down.")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
