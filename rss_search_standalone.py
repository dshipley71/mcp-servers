#!/usr/bin/env python3
"""
rss_topic_search.py
─────────────────────────────────────────────────────────────────────────────
Search 33 free RSS news feeds for a specific topic, deduplicate results,
and render structured JSON to stdout via the Rich library.

Usage:
    python rss_topic_search.py                      # uses built-in QUERY
    python rss_topic_search.py "my search term"     # custom query
    python rss_topic_search.py "term" --save out.json  # also write to file

Dependencies:
    pip install httpx feedparser beautifulsoup4 rich python-dateutil

All feeds in this script are free and require no API key.
Paywalled or API-key-required feeds have been intentionally excluded.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
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

DEFAULT_QUERY   = "Shield of Americas Summit"
MAX_ARTICLES    = 15
REQUEST_TIMEOUT = 20          # seconds per feed
MAX_CONCURRENT  = 10          # parallel feed fetches
RETRY_ATTEMPTS  = 2           # retries on transient server errors
SUMMARY_MAX_LEN = 500         # characters before truncation
CONTENT_MAX_LEN = 2000        # characters before truncation

# Full browser-style headers reduce 403 / bot-block rates
_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml, application/atom+xml, "
        "application/xml, text/xml, */*; q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

console = Console(stderr=True)


# ─────────────────────────────────────────────────────────────────────────────
# Feed registry  (33 free, no-key sources)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeedSource:
    name: str
    url_template: str    # use {query} for search feeds
    is_search: bool      # True → provider pre-filters by query
    category: str
    region: str


def _feed_url(src: FeedSource, query: str) -> str:
    return src.url_template.format(query=quote_plus(query)) if src.is_search else src.url_template


FEEDS: list[FeedSource] = [

    # ── Search feeds (best coverage for specific terms) ───────────────────
    FeedSource("Google News",
               "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
               True,  "Aggregator",   "Global"),
    FeedSource("Bing News",
               "https://www.bing.com/news/search?q={query}&format=RSS",
               True,  "Aggregator",   "Global"),
    FeedSource("Yahoo News",
               "https://news.search.yahoo.com/news/rss?p={query}",
               True,  "Aggregator",   "Global"),

    # ── Wire services ─────────────────────────────────────────────────────
    FeedSource("Reuters – World",
               "https://feeds.reuters.com/reuters/worldNews",
               False, "Wire Service", "Global"),
    FeedSource("Reuters – Politics",
               "https://feeds.reuters.com/Reuters/PoliticsNews",
               False, "Wire Service", "Global"),
    FeedSource("AP – Top Headlines",
               "https://rsshub.app/apnews/topics/ap-top-news",
               False, "Wire Service", "Global"),
    FeedSource("AP – International",
               "https://rsshub.app/apnews/topics/international-news",
               False, "Wire Service", "Global"),

    # ── Broadcasters ─────────────────────────────────────────────────────
    FeedSource("BBC – World",
               "http://feeds.bbci.co.uk/news/world/rss.xml",
               False, "Broadcaster",  "Global"),
    FeedSource("BBC – Americas",
               "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
               False, "Broadcaster",  "Americas"),
    FeedSource("Al Jazeera",
               "https://www.aljazeera.com/xml/rss/all.xml",
               False, "Broadcaster",  "Global"),
    FeedSource("Deutsche Welle",
               "https://rss.dw.com/rdf/rss-en-all",
               False, "Broadcaster",  "Global"),
    FeedSource("France 24 – Americas",
               "https://www.france24.com/en/americas/rss",
               False, "Broadcaster",  "Americas"),
    FeedSource("RFI English",
               "https://www.rfi.fr/en/rss",
               False, "Broadcaster",  "Global"),
    FeedSource("VOA News",
               "https://feeds.voanews.com/voaspecialenglish/latestnews",
               False, "Broadcaster",  "Global"),

    # ── US print / digital ────────────────────────────────────────────────
    FeedSource("NPR – News",
               "https://feeds.npr.org/1001/rss.xml",
               False, "US Media",     "US"),
    FeedSource("NPR – World",
               "https://feeds.npr.org/1004/rss.xml",
               False, "US Media",     "Global"),
    FeedSource("ABC News – International",
               "https://abcnews.go.com/abcnews/internationalheadlines",
               False, "US Media",     "Global"),
    FeedSource("CBS News – World",
               "https://www.cbsnews.com/latest/rss/world",
               False, "US Media",     "Global"),
    FeedSource("Fox News – World",
               "https://moxie.foxnews.com/google-publisher/world.xml",
               False, "US Media",     "Global"),
    FeedSource("The Hill",
               "https://thehill.com/feed/",
               False, "US Media",     "US"),
    FeedSource("Politico",
               "https://www.politico.com/rss/politics08.xml",
               False, "US Media",     "US"),
    FeedSource("The Guardian – World",
               "https://www.theguardian.com/world/rss",
               False, "Int'l Print",  "Global"),
    FeedSource("The Guardian – Americas",
               "https://www.theguardian.com/world/americas/rss",
               False, "Int'l Print",  "Americas"),
    FeedSource("Time Magazine",
               "https://time.com/feed/",
               False, "Int'l Print",  "Global"),

    # ── Foreign policy / think tanks ─────────────────────────────────────
    FeedSource("Foreign Policy",
               "https://foreignpolicy.com/feed/",
               False, "Think Tank",   "Global"),
    FeedSource("Council on Foreign Relations",
               "https://www.cfr.org/rss.xml",
               False, "Think Tank",   "Global"),
    FeedSource("Just Security",
               "https://www.justsecurity.org/feed/",
               False, "Think Tank",   "Global"),

    # ── Defense / security ────────────────────────────────────────────────
    FeedSource("Defense News",
               "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
               False, "Defense",      "Global"),
    FeedSource("Breaking Defense",
               "https://breakingdefense.com/feed/",
               False, "Defense",      "Global"),
    FeedSource("The Defense Post",
               "https://www.thedefensepost.com/feed/",
               False, "Defense",      "Global"),

    # ── Latin-America specialists ─────────────────────────────────────────
    FeedSource("Mercopress",
               "https://en.mercopress.com/rss.xml",
               False, "Regional",     "Americas"),
    FeedSource("Dialogo Americas (SOUTHCOM)",
               "https://dialogo-americas.com/en/feed/",
               False, "Regional",     "Americas"),
    FeedSource("InSight Crime",
               "https://insightcrime.org/feed/",
               False, "Regional",     "Americas"),
    FeedSource("Latin American Herald Tribune",
               "https://laht.com/feed/",
               False, "Regional",     "Americas"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Article:
    title: str
    url: str
    source: str
    source_category: str
    source_region: str
    published_iso: Optional[str]
    published_epoch: Optional[int]   # UTC epoch seconds
    author: Optional[str]
    summary: str
    content: str
    tags: list[str]
    matched_fields: list[str]        # which fields matched the query
    feed_url: str                    # URL that was fetched


@dataclass
class FeedResult:
    source: FeedSource
    articles: list[Article] = field(default_factory=list)
    error: Optional[str]    = None
    entry_count: int        = 0      # total entries in feed before filtering


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_html(html: str, max_len: int = 0) -> str:
    """Strip HTML, normalise whitespace, optional truncation."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        return text[:max_len] + "…"
    return text


def _parse_date(entry) -> tuple[Optional[str], Optional[int]]:
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not raw:
        return None, None
    try:
        dt = dateparser.parse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), int(dt.timestamp())
    except Exception:
        return str(raw), None


def _query_hits(entry, query: str) -> list[str]:
    """Return field names that contain the query (case-insensitive)."""
    q = query.lower()
    probe = {
        "title":   getattr(entry, "title", "") or "",
        "summary": getattr(entry, "summary", "") or "",
        "content": (
            entry.content[0].get("value", "")
            if getattr(entry, "content", None) else ""
        ),
        "tags": " ".join(
            t.get("term", "") for t in (getattr(entry, "tags", []) or [])
        ),
    }
    return [f for f, txt in probe.items() if q in _clean_html(txt).lower()]


def _author_name(entry) -> Optional[str]:
    raw = getattr(entry, "author_detail", None)
    if isinstance(raw, dict):
        return raw.get("name")
    raw = getattr(entry, "author", None)
    return str(raw).strip() if raw else None


def _entry_tags(entry) -> list[str]:
    return [
        t.get("term", "").strip()
        for t in (getattr(entry, "tags", []) or [])
        if t.get("term", "").strip()
    ]


def _entry_to_article(entry, src: FeedSource, query: str) -> Optional[Article]:
    title = _clean_html(getattr(entry, "title", "") or "")
    url   = getattr(entry, "link", "") or ""
    if not title or not url:
        return None

    # Search feeds are pre-filtered by provider; general feeds require a match
    matched = (
        ["search_feed"]
        if src.is_search
        else _query_hits(entry, query)
    )
    if not matched:
        return None

    iso_date, epoch = _parse_date(entry)

    raw_summary = getattr(entry, "summary", "") or ""
    raw_content = (
        entry.content[0].get("value", "")
        if getattr(entry, "content", None) else ""
    )
    summary = _clean_html(raw_summary, SUMMARY_MAX_LEN)
    content = _clean_html(raw_content, CONTENT_MAX_LEN) or summary

    return Article(
        title=title,
        url=url,
        source=src.name,
        source_category=src.category,
        source_region=src.region,
        published_iso=iso_date,
        published_epoch=epoch,
        author=_author_name(entry),
        summary=summary,
        content=content,
        tags=_entry_tags(entry),
        matched_fields=matched,
        feed_url=_feed_url(src, query),
    )


def _deduplicate(articles: list[Article]) -> list[Article]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[Article] = []
    for art in articles:
        url_key   = art.url.split("?")[0].rstrip("/").lower()
        title_key = re.sub(r"[^a-z0-9 ]", "", art.title.lower())
        title_key = re.sub(r"\s+", " ", title_key).strip()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(art)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Async fetching
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_one(
    client: httpx.AsyncClient,
    src: FeedSource,
    query: str,
    sem: asyncio.Semaphore,
    progress,
    task_id,
) -> FeedResult:
    url    = _feed_url(src, query)
    result = FeedResult(source=src)
    status = f"[red]✗[/] {src.name}: unknown error"

    for attempt in range(RETRY_ATTEMPTS):
        try:
            async with sem:
                resp = await client.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()

            parsed = feedparser.parse(resp.text)
            if parsed.get("bozo") and not parsed.entries:
                raise ValueError(str(parsed.get("bozo_exception", "Parse error")))

            result.entry_count = len(parsed.entries)
            for entry in parsed.entries:
                art = _entry_to_article(entry, src, query)
                if art:
                    result.articles.append(art)

            status = (
                f"[green]✓[/] {src.name}  "
                f"[dim]({result.entry_count} entries, "
                f"{len(result.articles)} hits)[/]"
            )
            break  # success — exit retry loop

        except httpx.HTTPStatusError as exc:
            result.error = f"HTTP {exc.response.status_code}"
            if exc.response.status_code < 500:
                break   # 4xx — pointless to retry
            await asyncio.sleep(1.5 * (attempt + 1))
        except Exception as exc:
            result.error = str(exc)[:80]
            await asyncio.sleep(1.0)

    if result.error:
        status = f"[red]✗[/] {src.name}  [dim]{result.error}[/]"

    progress.update(task_id, advance=1, description=status)
    return result


async def _fetch_all(query: str) -> list[FeedResult]:
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description:<60}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Connecting…", total=len(FEEDS))
        async with httpx.AsyncClient(
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            results = await asyncio.gather(
                *[_fetch_one(client, src, query, sem, progress, task_id) for src in FEEDS],
                return_exceptions=False,
            )
    return list(results)


# ─────────────────────────────────────────────────────────────────────────────
# Rich display helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_feed_health(results: list[FeedResult]) -> None:
    t = Table(title="Feed Health Report", header_style="bold cyan", show_lines=False)
    t.add_column("Source",    max_width=32)
    t.add_column("Category",  style="yellow",  width=14)
    t.add_column("Region",    style="magenta",  width=9)
    t.add_column("Entries",   justify="right",  width=8)
    t.add_column("Hits",      justify="right",  width=6)
    t.add_column("Status",    width=22)

    for r in sorted(results, key=lambda x: (bool(x.error), x.source.name)):
        if r.error:
            status_txt = Text(r.error[:20], style="red")
        else:
            status_txt = Text("OK", style="green bold")
        t.add_row(
            r.source.name,
            r.source.category,
            r.source.region,
            str(r.entry_count),
            str(len(r.articles)),
            status_txt,
        )
    console.print(t)


def _print_results_table(articles: list[Article], query: str) -> None:
    t = Table(
        title=f'Top {len(articles)} articles matching "{query}"',
        header_style="bold green",
        show_lines=True,
    )
    t.add_column("#",         style="dim",      width=3)
    t.add_column("Title",                       max_width=50)
    t.add_column("Source",    style="magenta",  max_width=24)
    t.add_column("Category",  style="yellow",   width=14)
    t.add_column("Region",    style="cyan",     width=9)
    t.add_column("Published",                   width=12)
    t.add_column("Matched",   style="dim",      width=18)

    for i, art in enumerate(articles, 1):
        pub     = (art.published_iso or "—")[:10]
        matched = ", ".join(art.matched_fields)
        t.add_row(
            str(i),
            art.title,
            art.source,
            art.source_category,
            art.source_region,
            pub,
            matched,
        )
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main(query: str, save_path: Optional[Path] = None) -> None:
    console.print(Rule("[bold green]RSS Topic Search[/]"))
    console.print(
        Panel(
            f"[bold]Query    :[/] [cyan]{query}[/]\n"
            f"[bold]Feeds    :[/] {len(FEEDS)}\n"
            f"[bold]Limit    :[/] {MAX_ARTICLES} articles",
            border_style="green",
        )
    )

    results  = await _fetch_all(query)

    # Flatten, sort, deduplicate, cap
    raw: list[Article] = []
    for r in results:
        raw.extend(r.articles)

    # Search-feed hits first, then newest-first
    raw.sort(key=lambda a: (
        0 if "search_feed" in a.matched_fields else 1,
        -(a.published_epoch or 0),
    ))

    deduped = _deduplicate(raw)
    final   = deduped[:MAX_ARTICLES]

    console.print()
    _print_feed_health(results)
    console.print()

    feeds_ok    = sum(1 for r in results if not r.error)
    feeds_fail  = len(results) - feeds_ok

    summary_table = Table.grid(padding=(0, 4))
    summary_table.add_row(
        Text(f"Feeds OK: {feeds_ok}", style="green bold"),
        Text(f"Failed: {feeds_fail}", style="red"),
        Text(f"Raw matches: {len(raw)}", style="cyan"),
        Text(f"After dedup: {len(deduped)}", style="yellow"),
        Text(f"Returned: {len(final)}", style="bold white"),
    )
    console.print(summary_table)
    console.print()

    if not final:
        console.print(
            Panel(
                "[yellow]No articles matched this query in the available feeds.\n"
                "Try a broader term, or run the script when more feeds are accessible.[/]",
                border_style="yellow",
                title="[bold yellow]No Results[/]",
            )
        )
        return

    _print_results_table(final, query)
    console.print()
    console.rule("[bold]JSON Output (stdout)[/]")

    # ── Assemble output document ─────────────────────────────────────────
    output: dict = {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feeds_searched": len(FEEDS),
        "feeds_ok": feeds_ok,
        "feeds_failed": feeds_fail,
        "raw_matches": len(raw),
        "after_dedup": len(deduped),
        "total_results": len(final),
        "max_articles": MAX_ARTICLES,
        "articles": [asdict(a) for a in final],
    }

    json_str = json.dumps(output, ensure_ascii=False, indent=2)

    # Rich-formatted, syntax-highlighted JSON → stdout
    print_json(json_str)

    # Optional file save
    if save_path:
        save_path.write_text(json_str, encoding="utf-8")
        console.print(
            f"\n[green]✓[/] Results saved to [cyan]{save_path}[/]",
            highlight=False,
        )


if __name__ == "__main__":
    args = sys.argv[1:]

    # Parse --save <filepath> flag
    save_file: Optional[Path] = None
    if "--save" in args:
        idx = args.index("--save")
        if idx + 1 < len(args):
            save_file = Path(args[idx + 1])
            args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    query = " ".join(args).strip() or DEFAULT_QUERY

    asyncio.run(main(query, save_file))
