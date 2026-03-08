#!/usr/bin/env python3
"""
gdelt_search_mcp.py — GDELT news search via the mcp-gdelt MCP server.

All GDELT API calls are routed through the mcp-gdelt Python MCP server using
the Model Context Protocol stdio transport. The server is spawned automatically
as a subprocess; no manual server startup is required.

Usage examples
--------------
# Default: search articles for "Shield of Americas Summit"
python gdelt_search_mcp.py

# Search articles — custom timespan and sort
python gdelt_search_mcp.py --mode articles --timespan 7d --sort ToneAsc

# Search images — with image type override
python gdelt_search_mcp.py --mode images --image-type imagewebtag

# Run both modes sequentially
python gdelt_search_mcp.py --mode all

# Custom query, more results, save JSON
python gdelt_search_mcp.py --query "Americas defense summit" -n 100 --output results.json

# Precise date range
python gdelt_search_mcp.py --mode articles --start 20250101000000 --end 20250301235959

# Point to a non-default server location
python gdelt_search_mcp.py --server-dir /path/to/mcp-gdelt-python
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich import box
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_QUERY     = '"Shield of Americas Summit"'
DEFAULT_MAX       = 75
DEFAULT_TIMESPAN  = "1month"
DEFAULT_SORT      = "DateDesc"
DEFAULT_IMAGE_TYPE = "imagetag"

# Path to the mcp-gdelt-python package (sibling directory by default)
_HERE = Path(__file__).resolve().parent
DEFAULT_SERVER_DIR = _HERE / "mcp-gdelt-python"

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# MCP client helpers
# ---------------------------------------------------------------------------

def _server_params(server_dir: Path) -> StdioServerParameters:
    """Build StdioServerParameters for the mcp-gdelt server."""
    src_dir = server_dir / "src"
    if not src_dir.exists():
        console.print(
            f"[red]Server source not found at {src_dir}\n"
            f"Use --server-dir to point to your mcp-gdelt-python directory.[/red]"
        )
        sys.exit(1)
    return StdioServerParameters(
        command=sys.executable,            # same Python interpreter
        args=["-m", "mcp_gdelt.server"],
        cwd=str(src_dir),                  # PYTHONPATH=src via cwd trick
        env=None,
    )


def _extract_text(result: Any) -> str:
    """Pull the text payload out of a CallToolResult."""
    for block in result.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _parse_tool_result(result: Any, tool_name: str) -> dict[str, Any]:
    """Return parsed JSON from a CallToolResult, raising on error."""
    if result.isError:
        raise RuntimeError(f"Tool '{tool_name}' returned an error: {_extract_text(result)}")
    raw = _extract_text(result)
    if not raw:
        raise RuntimeError(f"Tool '{tool_name}' returned empty content")
    return json.loads(raw)


async def _call_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call an MCP tool and return parsed JSON response."""
    result = await session.call_tool(tool_name, arguments)
    return _parse_tool_result(result, tool_name)


# ---------------------------------------------------------------------------
# Tool argument builders
# ---------------------------------------------------------------------------

def _articles_args(args: argparse.Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"query": args.query}
    if args.max_records:
        kwargs["max_records"] = args.max_records
    if args.timespan and not (args.start or args.end):
        kwargs["timespan"] = args.timespan
    if args.sort:
        kwargs["sort"] = args.sort
    if args.start:
        kwargs["start_date_time"] = args.start
    if args.end:
        kwargs["end_date_time"] = args.end
    return kwargs


def _images_args(args: argparse.Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"query": args.query}
    if args.max_records:
        kwargs["max_records"] = args.max_records
    if args.timespan and not (args.start or args.end):
        kwargs["timespan"] = args.timespan
    if args.image_type:
        kwargs["image_type"] = args.image_type
    return kwargs


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------

def _header(query: str, tool: str) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(Rule(style="bold blue"))
    console.print(
        Panel(
            f"[bold cyan]GDELT MCP Client[/bold cyan]  ·  "
            f"[dim]via mcp-gdelt server[/dim]\n"
            f"[yellow]Query:[/yellow]  {query}\n"
            f"[yellow]Tool:[/yellow]   [bold]{tool}[/bold]\n"
            f"[yellow]Time:[/yellow]   {ts}",
            box=box.ROUNDED,
            style="bold",
        )
    )


def _display_articles(data: dict[str, Any], query: str) -> None:
    """Render article list response."""
    _header(query, "search_articles")

    articles: list[dict] = data.get("articles", [])
    if not articles:
        console.print("\n[yellow]No articles returned for this query / timespan.[/yellow]")
        return

    # Summary strip
    langs    = sorted({a.get("language", "?") for a in articles})
    countries = sorted({a.get("sourcecountry", "?") for a in articles})
    domains  = sorted({a.get("domain", "?") for a in articles})

    console.print(
        f"\n[bold green]✓ {len(articles)} articles[/bold green]"
        f"  |  Languages: [cyan]{', '.join(langs[:8])}"
        f"{'…' if len(langs) > 8 else ''}[/cyan]"
        f"  |  Countries: [cyan]{len(countries)}[/cyan]"
        f"  |  Domains: [cyan]{len(domains)}[/cyan]\n"
    )

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        expand=True,
        show_lines=True,
    )
    table.add_column("#",       style="dim",          width=4,  no_wrap=True)
    table.add_column("Title",   style="bold white",   ratio=50)
    table.add_column("Domain",  style="cyan",         ratio=18)
    table.add_column("Date",    style="yellow",       width=12, no_wrap=True)
    table.add_column("Lang",    style="green",        width=8,  no_wrap=True)
    table.add_column("Country", style="blue",         width=14, no_wrap=True)

    for i, art in enumerate(articles, 1):
        title = art.get("title") or art.get("url", "(no title)")
        seen  = art.get("seendate", "")
        if len(seen) >= 8:
            try:
                dt   = datetime.strptime(seen[:15], "%Y%m%dT%H%M%S")
                seen = dt.strftime("%Y-%m-%d")
            except ValueError:
                seen = seen[:8]
        table.add_row(
            str(i),
            Text(title[:140], overflow="ellipsis"),
            art.get("domain", ""),
            seen,
            art.get("language", "")[:8],
            art.get("sourcecountry", "")[:14],
        )

    console.print(table)


def _display_images(data: dict[str, Any], query: str) -> None:
    """Render image collage response."""
    _header(query, "search_images")

    images: list[dict] = data.get("images", [])
    if not images:
        console.print("\n[yellow]No images returned for this query / timespan.[/yellow]")
        return

    console.print(f"\n[bold green]✓ {len(images)} images[/bold green]\n")

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.SIMPLE_HEAD,
        expand=True,
        show_lines=False,
    )
    table.add_column("#",         style="dim",    width=4)
    table.add_column("Image URL", style="cyan",   ratio=65)
    table.add_column("Web Count", style="yellow", justify="right", width=10)
    table.add_column("W×H",       style="green",  width=12, no_wrap=True)
    table.add_column("Format",    style="blue",   width=8)

    for i, img in enumerate(images, 1):
        w = img.get("width")
        h = img.get("height")
        dims = f"{w}×{h}" if w and h else "?"
        web_count = str(img.get("webcount", img.get("imagewebcount", "?")))
        table.add_row(
            str(i),
            Text(img.get("url", ""), overflow="ellipsis"),
            web_count,
            dims,
            img.get("format", "?"),
        )

    console.print(table)


def _display_tools(tools: list[Any]) -> None:
    """Pretty-print the tools discovered from the MCP server."""
    table = Table(
        title="[bold cyan]MCP Server Tools[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
    )
    table.add_column("Tool Name",   style="bold cyan",  width=24)
    table.add_column("Description", style="white",      ratio=1)
    for tool in tools:
        table.add_row(tool.name, tool.description or "")
    console.print(table)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _build_output(
    results: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "server": "mcp-gdelt",
        "query": args.query,
        "mode": args.mode,
        "parameters": {
            "max_records":  args.max_records,
            "timespan":     args.timespan,
            "sort":         args.sort,
            "start":        args.start,
            "end":          args.end,
            "image_type":   args.image_type,
        },
        "result_count": len(results),
        "results": results,
    }


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[bold green]✓ JSON written → {path}[/bold green]")


# ---------------------------------------------------------------------------
# Core async runner
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Spawn the mcp-gdelt server, discover tools, run requested searches."""
    server_dir = Path(args.server_dir).expanduser().resolve()
    params     = _server_params(server_dir)

    console.print(
        Panel(
            f"[bold]GDELT MCP Client[/bold]\n"
            f"Query:  [cyan]{args.query}[/cyan]\n"
            f"Mode:   [yellow]{args.mode}[/yellow]   "
            f"Timespan: [green]{args.timespan}[/green]   "
            f"Sort: [green]{args.sort}[/green]\n"
            f"Server: [dim]{server_dir}[/dim]",
            style="bold blue",
        )
    )

    results: list[dict[str, Any]] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:

            # ── Handshake ────────────────────────────────────────────────
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Connecting to mcp-gdelt server…"),
                transient=True,
                console=console,
            ) as prog:
                prog.add_task("connect", total=None)
                await session.initialize()

            # Show discovered tools on first connect
            tool_list = await session.list_tools()
            _display_tools(tool_list.tools)

            # ── search_articles ──────────────────────────────────────────
            if args.mode in ("articles", "all"):
                art_args = _articles_args(args)
                console.print(
                    f"\n[bold]→ Calling [cyan]search_articles[/cyan][/bold]  "
                    f"[dim]{art_args}[/dim]"
                )
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[cyan]Fetching articles…"),
                    transient=True,
                    console=console,
                ) as prog:
                    prog.add_task("fetch", total=None)
                    try:
                        data = await _call_tool(session, "search_articles", art_args)
                    except Exception as exc:
                        console.print(f"[red]search_articles failed: {exc}[/red]")
                        data = {}

                _display_articles(data, args.query)
                results.append({
                    "tool": "search_articles",
                    "arguments": art_args,
                    "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                    "data": data,
                    "summary": {
                        "total_articles": len(data.get("articles", [])),
                        "languages": sorted({
                            a.get("language", "?")
                            for a in data.get("articles", [])
                        }),
                        "source_countries": sorted({
                            a.get("sourcecountry", "?")
                            for a in data.get("articles", [])
                        }),
                        "domains": sorted({
                            a.get("domain", "?")
                            for a in data.get("articles", [])
                        }),
                    },
                })

            # ── search_images ────────────────────────────────────────────
            if args.mode in ("images", "all"):
                img_args = _images_args(args)
                console.print(
                    f"\n[bold]→ Calling [cyan]search_images[/cyan][/bold]  "
                    f"[dim]{img_args}[/dim]"
                )
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[cyan]Fetching images…"),
                    transient=True,
                    console=console,
                ) as prog:
                    prog.add_task("fetch", total=None)
                    try:
                        data = await _call_tool(session, "search_images", img_args)
                    except Exception as exc:
                        console.print(f"[red]search_images failed: {exc}[/red]")
                        data = {}

                _display_images(data, args.query)
                results.append({
                    "tool": "search_images",
                    "arguments": img_args,
                    "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                    "data": data,
                    "summary": {
                        "total_images": len(data.get("images", [])),
                    },
                })

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GDELT news search client for the mcp-gdelt MCP server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query", "-q",
        default=DEFAULT_QUERY,
        help=f"Search query (default: {DEFAULT_QUERY!r})",
    )
    parser.add_argument(
        "--mode", "-m",
        default="articles",
        choices=["articles", "images", "all"],
        help="Which MCP tool(s) to call: articles | images | all (default: articles)",
    )
    parser.add_argument(
        "--max-records", "-n",
        dest="max_records",
        type=int,
        default=DEFAULT_MAX,
        metavar="N",
        help=f"Maximum records per tool call (1–250, default: {DEFAULT_MAX})",
    )
    parser.add_argument(
        "--timespan", "-t",
        default=DEFAULT_TIMESPAN,
        help=f'Search window, e.g. "1month", "7d", "24h" (default: {DEFAULT_TIMESPAN})',
    )
    parser.add_argument(
        "--sort", "-s",
        default=DEFAULT_SORT,
        choices=["DateDesc", "DateAsc", "ToneAsc", "ToneDesc", "HybridRel"],
        help=f"Article sort order (default: {DEFAULT_SORT})",
    )
    parser.add_argument(
        "--image-type",
        dest="image_type",
        default=DEFAULT_IMAGE_TYPE,
        choices=["imagetag", "imagewebtag", "imageocrmeta"],
        help=f"Image search type (default: {DEFAULT_IMAGE_TYPE})",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="YYYYMMDDHHMMSS",
        help="Precise start datetime (overrides --timespan)",
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="YYYYMMDDHHMMSS",
        help="Precise end datetime (overrides --timespan)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help="Write full JSON results to this file (default: gdelt_<timestamp>.json)",
    )
    parser.add_argument(
        "--server-dir",
        dest="server_dir",
        default=str(DEFAULT_SERVER_DIR),
        metavar="DIR",
        help=f"Path to the mcp-gdelt-python project root (default: {DEFAULT_SERVER_DIR})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        results = asyncio.run(run(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)

    # Final summary
    console.print(Rule(style="bold blue"))
    total_articles = sum(
        r["summary"].get("total_articles", 0)
        for r in results
        if r["tool"] == "search_articles"
    )
    total_images = sum(
        r["summary"].get("total_images", 0)
        for r in results
        if r["tool"] == "search_images"
    )
    parts = []
    if total_articles:
        parts.append(f"[cyan]{total_articles} articles[/cyan]")
    if total_images:
        parts.append(f"[cyan]{total_images} images[/cyan]")
    console.print(
        f"\n[bold green]Done.[/bold green]  "
        + ("  |  ".join(parts) if parts else "[dim]No results.[/dim]")
    )

    # Write JSON
    payload = _build_output(results, args)
    out_path = Path(args.output) if args.output else Path(
        f"gdelt_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    _write_json(payload, out_path)

    # Inline JSON preview
    if results:
        console.print("\n[bold]JSON preview (summary only):[/bold]")
        preview = {
            "generated_at": payload["generated_at"],
            "query":         payload["query"],
            "results": [
                {
                    "tool":    r["tool"],
                    "summary": r["summary"],
                }
                for r in results
            ],
        }
        console.print(RichJSON(json.dumps(preview, indent=2)))


if __name__ == "__main__":
    main()
