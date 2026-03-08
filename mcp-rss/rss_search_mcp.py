#!/usr/bin/env python3
"""
rss_search_mcp.py  (mcp-rss-python edition)
─────────────────────────────────────────────────────────────────────────────
Search free RSS news feeds for a specific topic by connecting to the
mcp-rss-python MCP server over stdio.  Results are deduplicated, ranked,
and rendered as Rich-formatted JSON to stdout.

Strategy
────────
  • Search feeds  (Google News / Bing / Yahoo) already filter by query in
    their URL, so we call  fetch_multiple_feeds  on the pre-built URLs.
  • General feeds  are fetched and filtered server-side via  search_feed_items,
    which scans title / summary / content / tags for the query string.

Both tool calls run concurrently; results are merged before deduplication.

Usage
─────
    python rss_search_mcp.py                              # built-in query
    python rss_search_mcp.py "my search term"             # custom query
    python rss_search_mcp.py "term" --save results.json   # also save file

Requirements
────────────
    pip install mcp httpx feedparser beautifulsoup4 bleach
                rich python-dateutil pydantic-settings

    The mcp-rss-python directory must exist at  MCP_SERVER_DIR  (see below).
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich import print_json
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_QUERY = "Shield of Americas Summit"
MAX_ARTICLES  = 15

# Path to the mcp-rss-python project root (the directory that contains src/).
# Override by setting the environment variable MCP_RSS_SERVER_DIR, or edit here.
import os
MCP_SERVER_DIR = Path(os.environ.get("MCP_RSS_SERVER_DIR", Path(__file__).parent / "mcp-rss-python"))

console = Console(stderr=True)


# ─────────────────────────────────────────────────────────────────────────────
# Feed registry
# ─────────────────────────────────────────────────────────────────────────────

def _q(query: str) -> str:
    return quote_plus(query)


def search_feed_metas(query: str) -> list[dict]:
    """
    Aggregator feeds that embed the query in their URL.
    The provider pre-filters results, so every returned item is relevant.

    Note: Yahoo News RSS was removed — it returns malformed XML.
    """
    return [
        {
            "name": "Google News",
            "url": f"https://news.google.com/rss/search?q={_q(query)}&hl=en-US&gl=US&ceid=US:en",
            "category": "Aggregator",
            "region": "Global",
        },
        {
            "name": "Bing News",
            "url": f"https://www.bing.com/news/search?q={_q(query)}&format=RSS",
            "category": "Aggregator",
            "region": "Global",
        },
    ]


# General feeds — fetched in full, filtered server-side by search_feed_items
#
# Removed feeds (broken as of 2026-03):
#   Reuters – World / Politics     : DNS failure (Reuters discontinued public RSS)
#   AP via rsshub.app (x2)         : HTTP 403 (rsshub.app blocks automated access)
#   VOA News                       : XML parse error (malformed feed)
#   Politico                       : HTTP 403 (blocks automated access)
#   CFR (Council on Foreign Rel.)  : HTTP 404 (feed URL no longer exists)
#   The Defense Post               : XML parse error (malformed feed)
#   Mercopress                     : HTTP 404 (feed URL no longer exists)
#   Dialogo Americas               : XML parse error (URL redirects to an image)
#   LAHT                           : HTTP 404 (feed URL no longer exists)
GENERAL_FEEDS: list[dict] = [
    # Broadcasters
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml",                       "name": "BBC – World",                  "category": "Broadcaster",  "region": "Global"},
    {"url": "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",         "name": "BBC – Americas",               "category": "Broadcaster",  "region": "Americas"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml",                        "name": "Al Jazeera",                   "category": "Broadcaster",  "region": "Global"},
    {"url": "https://rss.dw.com/rdf/rss-en-all",                               "name": "Deutsche Welle",               "category": "Broadcaster",  "region": "Global"},
    {"url": "https://www.france24.com/en/americas/rss",                         "name": "France 24 – Americas",         "category": "Broadcaster",  "region": "Americas"},
    {"url": "https://www.rfi.fr/en/rss",                                        "name": "RFI English",                  "category": "Broadcaster",  "region": "Global"},
    # US media
    {"url": "https://feeds.npr.org/1001/rss.xml",                               "name": "NPR – News",                   "category": "US Media",     "region": "US"},
    {"url": "https://feeds.npr.org/1004/rss.xml",                               "name": "NPR – World",                  "category": "US Media",     "region": "Global"},
    {"url": "https://abcnews.go.com/abcnews/internationalheadlines",            "name": "ABC News – International",     "category": "US Media",     "region": "Global"},
    {"url": "https://www.cbsnews.com/latest/rss/world",                         "name": "CBS News – World",             "category": "US Media",     "region": "Global"},
    {"url": "https://moxie.foxnews.com/google-publisher/world.xml",             "name": "Fox News – World",             "category": "US Media",     "region": "Global"},
    {"url": "https://thehill.com/feed/",                                        "name": "The Hill",                     "category": "US Media",     "region": "US"},
    {"url": "https://www.theguardian.com/world/rss",                            "name": "The Guardian – World",         "category": "Int'l Print",  "region": "Global"},
    {"url": "https://www.theguardian.com/world/americas/rss",                   "name": "The Guardian – Americas",      "category": "Int'l Print",  "region": "Americas"},
    {"url": "https://time.com/feed/",                                           "name": "Time Magazine",                "category": "Int'l Print",  "region": "Global"},
    # Think tanks / foreign policy
    {"url": "https://foreignpolicy.com/feed/",                                  "name": "Foreign Policy",               "category": "Think Tank",   "region": "Global"},
    {"url": "https://www.justsecurity.org/feed/",                               "name": "Just Security",                "category": "Think Tank",   "region": "Global"},
    # Defense / security
    {"url": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml","name": "Defense News",                 "category": "Defense",      "region": "Global"},
    {"url": "https://breakingdefense.com/feed/",                                "name": "Breaking Defense",             "category": "Defense",      "region": "Global"},
    # Latin America specialists
    {"url": "https://insightcrime.org/feed/",                                   "name": "InSight Crime",                "category": "Regional",     "region": "Americas"},
]

# URL → metadata lookup for annotating search_feed_items results
_FEED_META: dict[str, dict] = {f["url"]: f for f in GENERAL_FEEDS}


# ─────────────────────────────────────────────────────────────────────────────
# MCP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tool_text(result: Any) -> str:
    """Pull the text payload out of a CallToolResult."""
    for block in result.content:
        if hasattr(block, "text"):
            return block.text
    return "{}"


def _parse_tool_json(result: Any) -> Any:
    return json.loads(_tool_text(result))


# ─────────────────────────────────────────────────────────────────────────────
# Article normalisation
# ─────────────────────────────────────────────────────────────────────────────

def _clean(text: str | None, max_len: int = 0) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        return text[:max_len] + "…"
    return text


def _epoch_ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _epoch_ms_to_s(ms: int | None) -> int | None:
    return int(ms / 1000) if ms else None


def _item_to_article(item: dict, meta: dict, matched_fields: list[str], feed_url: str) -> dict | None:
    """Convert a FeedItem dict (from the MCP server) to a flat article dict."""
    title = _clean(item.get("title") or "")
    url   = item.get("url") or ""
    if not title or not url:
        return None
    return {
        "title":            title,
        "url":              url,
        "source":           meta.get("name", "Unknown"),
        "source_category":  meta.get("category", "Unknown"),
        "source_region":    meta.get("region", "Global"),
        "published_iso":    _epoch_ms_to_iso(item.get("published")),
        "published_epoch":  _epoch_ms_to_s(item.get("published")),
        "author":           item.get("author"),
        "summary":          _clean(item.get("description") or item.get("content") or "", 500),
        "content":          _clean(item.get("content") or item.get("description") or "", 2000),
        "tags":             item.get("categories") or [],
        "matched_fields":   matched_fields,
        "feed_url":         feed_url,
    }


def _from_multi_feed_result(multi: dict, metas: list[dict]) -> list[dict]:
    """Parse fetch_multiple_feeds response into flat article list."""
    articles: list[dict] = []
    for result, meta in zip(multi.get("results", []), metas):
        if not result.get("success") or not result.get("data"):
            continue
        feed_data = result["data"]
        for item in feed_data.get("items", []):
            art = _item_to_article(item, meta, ["search_feed"], meta["url"])
            if art:
                articles.append(art)
    return articles


def _from_search_result(search: dict) -> list[dict]:
    """Parse search_feed_items response into flat article list."""
    articles: list[dict] = []
    for hit in search.get("results", []):
        item     = hit.get("item", {})
        feed_url = hit.get("feedUrl", "")
        meta     = _FEED_META.get(feed_url, {"name": hit.get("feedTitle", "Unknown"),
                                              "category": "Unknown", "region": "Global"})
        art = _item_to_article(item, meta, hit.get("matches") or ["content"], feed_url)
        if art:
            articles.append(art)
    return articles


def _deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls:   set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for art in articles:
        uk = (art.get("url") or "").split("?")[0].rstrip("/").lower()
        tk = re.sub(r"[^a-z0-9 ]", "", (art.get("title") or "").lower())
        tk = re.sub(r"\s+", " ", tk).strip()
        if not uk or uk in seen_urls:
            continue
        if tk and tk in seen_titles:
            continue
        seen_urls.add(uk)
        if tk:
            seen_titles.add(tk)
        unique.append(art)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Core async search
# ─────────────────────────────────────────────────────────────────────────────

async def _run_search(query: str) -> tuple[list[dict], dict]:
    """
    Open a single MCP session, fire both tool calls concurrently, return results.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.server"],
        cwd=str(MCP_SERVER_DIR),
    )

    sf_metas = search_feed_metas(query)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Calling MCP tools…", total=2)

                # ── Tool call 1: fetch_multiple_feeds (search feeds) ──────
                progress.update(
                    task,
                    description=(
                        "[cyan]fetch_multiple_feeds[/] — "
                        f"{len(sf_metas)} search feeds…"
                    ),
                )
                multi_raw = await session.call_tool(
                    "fetch_multiple_feeds",
                    {
                        "urls":     [m["url"] for m in sf_metas],
                        "parallel": "true",
                    },
                )
                progress.advance(task)

                # ── Tool call 2: search_feed_items (general feeds) ────────
                progress.update(
                    task,
                    description=(
                        "[cyan]search_feed_items[/] — "
                        f"{len(GENERAL_FEEDS)} general feeds…"
                    ),
                )
                search_raw = await session.call_tool(
                    "search_feed_items",
                    {
                        "feeds":     [f["url"] for f in GENERAL_FEEDS],
                        "query":     query,
                        "search_in": "all",
                    },
                )
                progress.advance(task)

    # ── Merge ─────────────────────────────────────────────────────────────
    multi_data  = _parse_tool_json(multi_raw)
    search_data = _parse_tool_json(search_raw)

    articles: list[dict] = []
    articles.extend(_from_multi_feed_result(multi_data, sf_metas))
    articles.extend(_from_search_result(search_data))

    stats = {
        "search_feeds_total":    len(sf_metas),
        "search_feeds_ok":       multi_data.get("successful", 0),
        "search_feeds_failed":   multi_data.get("failed", 0),
        "general_feeds_searched":search_data.get("feedsSearched", len(GENERAL_FEEDS)),
        "raw_matches":           len(articles),
    }
    return articles, stats


# ─────────────────────────────────────────────────────────────────────────────
# Rich display
# ─────────────────────────────────────────────────────────────────────────────

def _print_results_table(articles: list[dict], query: str) -> None:
    t = Table(
        title=f'Top {len(articles)} articles — "{query}"',
        header_style="bold green",
        show_lines=True,
    )
    t.add_column("#",         style="dim",      width=3)
    t.add_column("Title",                        max_width=50)
    t.add_column("Source",    style="magenta",   max_width=24)
    t.add_column("Category",  style="yellow",    width=14)
    t.add_column("Region",    style="cyan",      width=9)
    t.add_column("Published",                    width=12)
    t.add_column("Matched",   style="dim",       width=18)

    for i, art in enumerate(articles, 1):
        pub     = (art.get("published_iso") or "—")[:10]
        matched = ", ".join(art.get("matched_fields") or [])
        t.add_row(
            str(i),
            art.get("title", ""),
            art.get("source", ""),
            art.get("source_category", ""),
            art.get("source_region", ""),
            pub,
            matched,
        )
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main(query: str, save_path: Optional[Path] = None) -> None:
    # Validate server path before connecting
    if not (MCP_SERVER_DIR / "src" / "server.py").exists():
        console.print(
            Panel(
                f"[red]mcp-rss-python server not found at:[/]\n"
                f"  [cyan]{MCP_SERVER_DIR}[/]\n\n"
                "Set the  [bold]MCP_RSS_SERVER_DIR[/]  environment variable, or place\n"
                "mcp-rss-python/ in the same directory as this script.",
                title="[bold red]Configuration Error[/]",
                border_style="red",
            )
        )
        sys.exit(1)

    total_feeds = len(GENERAL_FEEDS) + 3
    console.print(Rule("[bold green]RSS Topic Search  ·  mcp-rss-python[/]"))
    console.print(
        Panel(
            f"[bold]Query   :[/] [cyan]{query}[/]\n"
            f"[bold]Server  :[/] {MCP_SERVER_DIR}\n"
            f"[bold]Feeds   :[/] {total_feeds}  "
            f"([yellow]3[/] search + [yellow]{len(GENERAL_FEEDS)}[/] general)\n"
            f"[bold]Tools   :[/] fetch_multiple_feeds  +  search_feed_items\n"
            f"[bold]Limit   :[/] {MAX_ARTICLES} articles",
            border_style="green",
        )
    )

    raw_articles, stats = await _run_search(query)

    # Sort: search-feed hits first, then newest-first
    raw_articles.sort(key=lambda a: (
        0 if "search_feed" in (a.get("matched_fields") or []) else 1,
        -(a.get("published_epoch") or 0),
    ))

    deduped = _deduplicate(raw_articles)
    final   = deduped[:MAX_ARTICLES]

    # Stats bar
    console.print()
    sg = Table.grid(padding=(0, 4))
    sg.add_row(
        Text(f"Search feeds OK: {stats['search_feeds_ok']}/{stats['search_feeds_total']}", style="green bold"),
        Text(f"Search feeds failed: {stats['search_feeds_failed']}", style="red"),
        Text(f"General feeds searched: {stats['general_feeds_searched']}", style="cyan"),
        Text(f"Raw matches: {stats['raw_matches']}", style="yellow"),
        Text(f"After dedup: {len(deduped)}", style="yellow"),
        Text(f"Returned: {len(final)}", style="bold white"),
    )
    console.print(sg)
    console.print()

    if not final:
        console.print(
            Panel(
                "[yellow]No articles matched this query.\n"
                "Try a broader search term, or check that the feeds are reachable.[/]",
                border_style="yellow",
                title="[bold yellow]No Results[/]",
            )
        )
        return

    _print_results_table(final, query)
    console.print()
    console.rule("[bold]JSON Output[/]")

    output = {
        "query":                  query,
        "generated_at":           datetime.now(timezone.utc).isoformat(),
        "mcp_server":             str(MCP_SERVER_DIR),
        "tools_used":             ["fetch_multiple_feeds", "search_feed_items"],
        "total_feeds":            total_feeds,
        "search_feeds_ok":        stats["search_feeds_ok"],
        "search_feeds_failed":    stats["search_feeds_failed"],
        "general_feeds_searched": stats["general_feeds_searched"],
        "raw_matches":            stats["raw_matches"],
        "after_dedup":            len(deduped),
        "total_results":          len(final),
        "max_articles":           MAX_ARTICLES,
        "articles":               final,
    }

    json_str = json.dumps(output, ensure_ascii=False, indent=2)
    print_json(json_str)

    if save_path:
        save_path.write_text(json_str, encoding="utf-8")
        console.print(
            f"\n[green]✓[/] Saved to [cyan]{save_path}[/]",
            highlight=False,
        )


if __name__ == "__main__":
    args = sys.argv[1:]

    save_file: Optional[Path] = None
    if "--save" in args:
        idx = args.index("--save")
        if idx + 1 < len(args):
            save_file = Path(args[idx + 1])
            args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    query = " ".join(args).strip() or DEFAULT_QUERY
    asyncio.run(main(query, save_file))
