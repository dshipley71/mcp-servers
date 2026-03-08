#!/usr/bin/env python3
"""
gdelt_search.py — GDELT DOC 2.0 API multi-mode news search tool.

Usage examples
--------------
# Default: ArtList for "Shield of Americas Summit"
python gdelt_search.py

# Custom query, mode, timespan
python gdelt_search.py --query "Shield of Americas Summit" --mode artlist --timespan 3months

# All modes in one shot
python gdelt_search.py --mode all

# Article list, sorted by tone, last 7 days, save JSON
python gdelt_search.py --mode artlist --sort ToneAsc --timespan 7d --output results.json

# Timeline of coverage volume
python gdelt_search.py --mode timelinevol --timespan 1month

# Tone chart across the last month
python gdelt_search.py --mode tonechart

# Image search by visual AI tag
python gdelt_search.py --mode imagecollageinfo --query "Shield of Americas Summit"

# Precise date range
python gdelt_search.py --mode artlist --start 20250101000000 --end 20250301235959
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_QUERY = '"Shield of Americas Summit"'
DEFAULT_MAX_RECORDS = 75
DEFAULT_TIMESPAN = "1month"
DEFAULT_SORT = "DateDesc"

VALID_MODES = Literal[
    "artlist",
    "artgallery",
    "timelinevol",
    "timelinevolraw",
    "timelinevolinfo",
    "timelinetone",
    "timelinelang",
    "timelinesourcecountry",
    "tonechart",
    "wordcloudimagetags",
    "wordcloudimagewebtags",
    "imagecollage",
    "imagecollageinfo",
    "imagegallery",
    "all",
]

ARTICLE_MODES = {
    "artlist": "ArtList",
    "artgallery": "ArtGallery",
}

TIMELINE_MODES = {
    "timelinevol": "TimelineVol",
    "timelinevolraw": "TimelineVolRaw",
    "timelinevolinfo": "TimelineVolInfo",
    "timelinetone": "TimelineTone",
    "timelinelang": "TimelineLang",
    "timelinesourcecountry": "TimelineSourceCountry",
}

IMAGE_MODES = {
    "imagecollage": "ImageCollage",
    "imagecollageinfo": "ImageCollageInfo",
    "imagegallery": "ImageGallery",
}

CHART_MODES = {
    "tonechart": "ToneChart",
    "wordcloudimagetags": "WordCloudImageTags",
    "wordcloudimagewebtags": "WordCloudImageWebTags",
}

ALL_MODES: dict[str, str] = {
    **ARTICLE_MODES,
    **TIMELINE_MODES,
    **IMAGE_MODES,
    **CHART_MODES,
}

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# GDELT API client
# ---------------------------------------------------------------------------

def build_params(
    query: str,
    mode: str,
    fmt: str = "JSON",
    max_records: int = DEFAULT_MAX_RECORDS,
    sort: str = DEFAULT_SORT,
    timespan: str | None = DEFAULT_TIMESPAN,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    timeline_smooth: int | None = None,
) -> dict[str, str]:
    """Build the flat query-param dict for a GDELT API request."""
    params: dict[str, str] = {
        "query": query,
        "mode": mode,
        "format": fmt,
        "maxrecords": str(max_records),
        "sort": sort,
    }
    if timespan and not (start_datetime or end_datetime):
        params["timespan"] = timespan
    if start_datetime:
        params["startdatetime"] = start_datetime
    if end_datetime:
        params["enddatetime"] = end_datetime
    if timeline_smooth is not None:
        params["TIMELINESMOOTH"] = str(min(30, max(1, timeline_smooth)))
    return params


def fetch_gdelt(
    query: str,
    mode_key: str,
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
    sort: str = DEFAULT_SORT,
    timespan: str | None = DEFAULT_TIMESPAN,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute one GDELT DOC 2.0 API request and return parsed JSON + metadata."""
    api_mode = ALL_MODES.get(mode_key, mode_key)
    params = build_params(
        query=query,
        mode=api_mode,
        max_records=max_records,
        sort=sort,
        timespan=timespan,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )

    url = f"{GDELT_BASE_URL}?{urlencode(params)}"

    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers={"User-Agent": "GDELT-Search/1.0"})
        response.raise_for_status()

    raw = response.json()

    # Wrap raw response in a normalised envelope
    return {
        "meta": {
            "query": query,
            "mode": api_mode,
            "mode_key": mode_key,
            "params": params,
            "request_url": url,
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
            "http_status": response.status_code,
        },
        "data": raw,
        "summary": _summarise(raw, mode_key),
    }


# ---------------------------------------------------------------------------
# Response normalisation helpers
# ---------------------------------------------------------------------------

def _summarise(raw: dict[str, Any], mode_key: str) -> dict[str, Any]:
    """Extract a human-readable summary dict from the raw GDELT response."""
    summary: dict[str, Any] = {}

    if mode_key in ARTICLE_MODES:
        articles = raw.get("articles", [])
        summary["total_articles"] = len(articles)
        summary["languages"] = sorted({a.get("language", "?") for a in articles})
        summary["source_countries"] = sorted({a.get("sourcecountry", "?") for a in articles})
        summary["domains"] = sorted({a.get("domain", "?") for a in articles})

    elif mode_key in TIMELINE_MODES:
        timeline = raw.get("timeline", [])
        summary["data_series"] = len(timeline)
        if timeline:
            first_series = timeline[0].get("data", [])
            summary["data_points"] = len(first_series)

    elif mode_key in IMAGE_MODES:
        images = raw.get("images", [])
        summary["total_images"] = len(images)

    elif mode_key == "tonechart":
        bins = raw.get("tonechart", [])
        summary["tone_bins"] = len(bins)
        if bins:
            tones = [b.get("tone", 0) for b in bins if b.get("tone") is not None]
            counts = [b.get("count", 0) for b in bins if b.get("count") is not None]
            summary["tone_range"] = [min(tones), max(tones)] if tones else []
            summary["total_articles_counted"] = sum(counts)

    return summary


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------

def _print_header(query: str, mode_key: str, api_mode: str) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(Rule(style="bold blue"))
    console.print(
        Panel(
            f"[bold cyan]GDELT DOC 2.0 News Search[/bold cyan]\n"
            f"[yellow]Query:[/yellow]  {query}\n"
            f"[yellow]Mode:[/yellow]   {api_mode}  ([dim]{mode_key}[/dim])\n"
            f"[yellow]Time:[/yellow]   {ts}",
            box=box.ROUNDED,
            style="bold",
        )
    )


def _display_artlist(data: dict[str, Any]) -> None:
    articles: list[dict] = data.get("data", {}).get("articles", [])
    if not articles:
        console.print("[red]No articles returned.[/red]")
        return

    summary = data["summary"]
    console.print(
        f"\n[bold green]✓ {summary['total_articles']} articles found[/bold green]  "
        f"| Languages: [cyan]{', '.join(summary['languages'][:8])}[/cyan]  "
        f"| Countries: [cyan]{len(summary['source_countries'])}[/cyan]\n"
    )

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        expand=True,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Title", style="bold white", ratio=45)
    table.add_column("Domain", style="cyan", ratio=18)
    table.add_column("Date", style="yellow", width=12, no_wrap=True)
    table.add_column("Lang", style="green", width=6, no_wrap=True)
    table.add_column("Country", style="blue", width=10, no_wrap=True)

    for i, art in enumerate(articles, 1):
        title = art.get("title") or art.get("url", "(no title)")
        seen = art.get("seendate", "")
        # Parse GDELT date format: 20250101T120000Z
        if len(seen) >= 8:
            try:
                dt = datetime.strptime(seen[:15], "%Y%m%dT%H%M%S")
                seen = dt.strftime("%Y-%m-%d")
            except ValueError:
                seen = seen[:8]
        table.add_row(
            str(i),
            Text(title[:120], overflow="ellipsis"),
            art.get("domain", ""),
            seen,
            art.get("language", "")[:6],
            art.get("sourcecountry", "")[:10],
        )

    console.print(table)


def _display_timeline(data: dict[str, Any], mode_key: str) -> None:
    raw = data.get("data", {})
    timeline: list[dict] = raw.get("timeline", [])
    if not timeline:
        console.print("[red]No timeline data returned.[/red]")
        return

    summary = data["summary"]
    console.print(
        f"\n[bold green]✓ {summary['data_series']} series "
        f"× {summary.get('data_points', '?')} data points[/bold green]\n"
    )

    for series in timeline:
        label = series.get("series", series.get("label", "Series"))
        pts: list[dict] = series.get("data", [])
        if not pts:
            continue

        table = Table(
            title=f"[bold cyan]{label}[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
            box=box.SIMPLE_HEAD,
        )
        table.add_column("Date / Time", style="yellow", width=22)

        value_key = "value" if "value" in pts[0] else list(pts[0].keys())[-1]
        col_label = "Volume %" if "vol" in mode_key.lower() else "Tone" if "tone" in mode_key.lower() else "Value"
        table.add_column(col_label, style="cyan", justify="right")

        if "norm" in pts[0]:
            table.add_column("Total Articles", style="dim", justify="right")

        # Show at most 40 rows
        step = max(1, len(pts) // 40)
        for pt in pts[::step]:
            row = [pt.get("date", ""), f"{pt.get(value_key, 0):.6f}"]
            if "norm" in pt:
                row.append(str(pt["norm"]))
            table.add_row(*row)

        console.print(table)

    # Top articles if present (TimelineVolInfo)
    if "topinfo" in raw:
        console.print("\n[bold]Top articles per time step (sample):[/bold]")
        for entry in list(raw["topinfo"].values())[:3]:
            for art in entry[:3]:
                console.print(
                    f"  [cyan]→[/cyan] [white]{art.get('title', 'N/A')}[/white] "
                    f"[dim]({art.get('domain', '')})[/dim]"
                )


def _display_tonechart(data: dict[str, Any]) -> None:
    bins: list[dict] = data.get("data", {}).get("tonechart", [])
    if not bins:
        console.print("[red]No tone chart data returned.[/red]")
        return

    summary = data["summary"]
    console.print(
        f"\n[bold green]✓ {summary['tone_bins']} tone bins, "
        f"{summary.get('total_articles_counted', '?')} articles, "
        f"tone range {summary.get('tone_range', ['?', '?'])}[/bold green]\n"
    )

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("Tone", style="yellow", justify="right", width=8)
    table.add_column("Count", style="cyan", justify="right", width=8)
    table.add_column("Bar", ratio=1)

    max_count = max((b.get("count", 0) for b in bins), default=1)
    for b in bins:
        tone = b.get("tone", 0)
        count = b.get("count", 0)
        bar_len = int((count / max_count) * 50)
        color = "green" if tone > 0 else "red" if tone < 0 else "yellow"
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        table.add_row(f"{tone:+.1f}", str(count), bar)

    console.print(table)


def _display_images(data: dict[str, Any]) -> None:
    images: list[dict] = data.get("data", {}).get("images", [])
    if not images:
        console.print("[red]No images returned.[/red]")
        return

    console.print(f"\n[bold green]✓ {len(images)} images found[/bold green]\n")

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Image URL", style="cyan", ratio=60)
    table.add_column("Web Count", style="yellow", justify="right", width=10)
    table.add_column("Format", style="green", width=8)

    for i, img in enumerate(images, 1):
        table.add_row(
            str(i),
            Text(img.get("url", ""), overflow="ellipsis"),
            str(img.get("webcount", img.get("imagewebcount", "?"))),
            img.get("format", "?"),
        )

    console.print(table)


def _display_wordcloud(data: dict[str, Any]) -> None:
    raw = data.get("data", {})
    tags = raw.get("tags", raw.get("webtags", []))
    if not tags:
        console.print("[red]No word cloud data returned.[/red]")
        return

    console.print(f"\n[bold green]✓ {len(tags)} tags[/bold green]\n")

    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE_HEAD)
    table.add_column("Tag", style="cyan")
    table.add_column("Count", style="yellow", justify="right")

    for tag in tags[:50]:
        table.add_row(tag.get("tag", ""), str(tag.get("count", "")))

    console.print(table)


def _display_result(result: dict[str, Any]) -> None:
    mode_key: str = result["meta"]["mode_key"]
    api_mode: str = result["meta"]["mode"]
    _print_header(result["meta"]["query"], mode_key, api_mode)

    if mode_key in ARTICLE_MODES:
        _display_artlist(result)
    elif mode_key in TIMELINE_MODES:
        _display_timeline(result, mode_key)
    elif mode_key == "tonechart":
        _display_tonechart(result)
    elif mode_key in IMAGE_MODES:
        _display_images(result)
    elif mode_key in CHART_MODES:
        _display_wordcloud(result)
    else:
        console.print(JSON(json.dumps(result["data"], indent=2)))

    console.print(f"\n[dim]Request URL: {result['meta']['request_url']}[/dim]")
    console.print(Rule(style="dim"))


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def write_json(results: list[dict[str, Any]], path: Path) -> None:
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "result_count": len(results),
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[bold green]✓ JSON written → {path}[/bold green]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search GDELT DOC 2.0 API across multiple modes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query", "-q",
        default=DEFAULT_QUERY,
        help=f'Search query (default: {DEFAULT_QUERY!r})',
    )
    parser.add_argument(
        "--mode", "-m",
        default="artlist",
        choices=list(ALL_MODES.keys()) + ["all"],
        help="API mode to run (default: artlist). Use 'all' to run every mode.",
    )
    parser.add_argument(
        "--max-records", "-n",
        type=int,
        default=DEFAULT_MAX_RECORDS,
        metavar="N",
        help=f"Maximum records to fetch per mode (1–250, default: {DEFAULT_MAX_RECORDS})",
    )
    parser.add_argument(
        "--timespan", "-t",
        default=DEFAULT_TIMESPAN,
        help=f'Time window, e.g. "1month", "7d", "24h" (default: {DEFAULT_TIMESPAN})',
    )
    parser.add_argument(
        "--sort", "-s",
        default=DEFAULT_SORT,
        choices=["DateDesc", "DateAsc", "ToneAsc", "ToneDesc", "HybridRel"],
        help=f"Sort order (default: {DEFAULT_SORT})",
    )
    parser.add_argument(
        "--start", default=None, metavar="YYYYMMDDHHMMSS",
        help="Precise start datetime (overrides --timespan)",
    )
    parser.add_argument(
        "--end", default=None, metavar="YYYYMMDDHHMMSS",
        help="Precise end datetime (overrides --timespan)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help="Write full JSON results to this file (e.g. results.json)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress rich display; only emit JSON output (requires --output)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def run_mode(
    mode_key: str,
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Fetch one mode and display it. Returns the result dict or None on error."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]Fetching [bold]{ALL_MODES[mode_key]}[/bold]…"),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("fetch", total=None)
            result = fetch_gdelt(
                query=args.query,
                mode_key=mode_key,
                max_records=args.max_records,
                sort=args.sort,
                timespan=args.timespan if not (args.start or args.end) else None,
                start_datetime=args.start,
                end_datetime=args.end,
                timeout=args.timeout,
            )

        if not args.json_only:
            _display_result(result)

        return result

    except httpx.HTTPStatusError as exc:
        console.print(
            f"[red]HTTP {exc.response.status_code} for mode {mode_key}: "
            f"{exc.response.text[:200]}[/red]"
        )
    except (httpx.ProxyError, httpx.ConnectError) as exc:
        console.print(
            f"[red]Network error for mode {mode_key}:[/red] {exc}\n"
            "[dim]If you are behind a proxy or firewall, ensure gdeltproject.org is reachable.[/dim]"
        )
    except httpx.TimeoutException:
        console.print(
            f"[red]Timeout fetching mode {mode_key}. Try --timeout 60 or a shorter --timespan.[/red]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error fetching mode {mode_key}: {exc}[/red]")

    return None


def main() -> None:
    args = parse_args()

    if args.json_only and not args.output:
        console.print("[red]--json-only requires --output FILE[/red]")
        sys.exit(1)

    modes_to_run = list(ALL_MODES.keys()) if args.mode == "all" else [args.mode]

    console.print(
        Panel(
            f"[bold]GDELT DOC 2.0 Search[/bold]\n"
            f"Query: [cyan]{args.query}[/cyan]   "
            f"Modes: [yellow]{', '.join(modes_to_run)}[/yellow]   "
            f"Timespan: [green]{args.timespan}[/green]",
            style="bold blue",
        )
    )

    all_results: list[dict[str, Any]] = []

    for mode_key in modes_to_run:
        result = run_mode(mode_key, args)
        if result:
            all_results.append(result)

    # Final summary
    console.print(
        f"\n[bold green]Completed {len(all_results)}/{len(modes_to_run)} modes "
        f"for query: {args.query}[/bold green]"
    )

    # Aggregate article quick-look across all article modes
    total_articles = sum(
        r["summary"].get("total_articles", 0)
        for r in all_results
        if r["meta"]["mode_key"] in ARTICLE_MODES
    )
    if total_articles:
        console.print(f"[cyan]Total articles collected: {total_articles}[/cyan]")

    # Write JSON
    if args.output:
        write_json(all_results, Path(args.output))
    elif all_results and not args.json_only:
        # Always emit a default JSON file named after the run
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_path = Path(f"gdelt_{ts}.json")
        write_json(all_results, default_path)


if __name__ == "__main__":
    main()
