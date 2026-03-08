# GDELT MCP Server (Python)

A [Model Context Protocol](https://modelcontextprotocol.io/) server that provides access to the **GDELT DOC 2.0 API** for searching global news articles and images. Python rewrite of the original TypeScript implementation.

## Features

- **search_articles** — search across 65 languages of global news coverage (rolling 3-month window)
- **search_images** — query the Visual Knowledge Graph (VGKG) for news imagery
- Optimised defaults: `ArtList` mode, JSON format, 50 records, newest-first, 1-month window
- Boolean queries: `OR`, `AND`, exact phrases in quotes
- Flexible timespan: 15 minutes → 3 months

## Requirements

- Python ≥ 3.11
- Dependencies: `mcp[cli]`, `httpx`, `pydantic`, `python-dotenv`

## Installation

```bash
# From source
pip install -e .

# Or install dependencies directly
pip install mcp[cli] httpx pydantic python-dotenv
```

## Configuration

```bash
cp .env.example .env   # then edit as needed
```

| Variable | Default | Description |
|---|---|---|
| `GDELT_API_TIMEOUT` | `30` | Request timeout in seconds |
| `GDELT_API_BASE_URL` | GDELT DOC 2.0 endpoint | Override API URL |
| `GDELT_DEFAULT_MAX_RECORDS` | `50` | Default result count (1–250) |
| `GDELT_DEFAULT_TIMESPAN` | `1month` | Default search window |
| `GDELT_USER_AGENT` | `GDELT-MCP-Server/1.0` | HTTP User-Agent |
| `LOG_LEVEL` | `info` | `debug` / `info` / `warn` / `error` |

## Running

```bash
# As an installed script
mcp-gdelt

# Or directly
python -m mcp_gdelt.server

# Or via the MCP CLI
mcp run src/mcp_gdelt/server.py
```

## MCP Client Configuration

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gdelt": {
      "command": "mcp-gdelt"
    }
  }
}
```

Or without installing:

```json
{
  "mcpServers": {
    "gdelt": {
      "command": "python",
      "args": ["-m", "mcp_gdelt.server"],
      "cwd": "/path/to/mcp-gdelt-python/src"
    }
  }
}
```

## Available Tools

### `search_articles`

Search GDELT's global news database for articles.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | ✓ | Keywords, quoted phrases, OR/AND operators |
| `max_records` | int | — | Results to return (1–250, default 50) |
| `timespan` | string | — | `"1month"`, `"7d"`, `"24h"` … |
| `sort` | string | — | `DateDesc` / `DateAsc` / `ToneAsc` / `ToneDesc` / `HybridRel` |
| `start_date_time` | string | — | `YYYYMMDDHHMMSS` |
| `end_date_time` | string | — | `YYYYMMDDHHMMSS` |

### `search_images`

Search GDELT's Visual Knowledge Graph for news images.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | ✓ | Search term, e.g. `"fire"`, `"protest"` |
| `max_records` | int | — | Results to return (1–250, default 50) |
| `timespan` | string | — | `"1month"`, `"7d"`, `"24h"` … |
| `image_type` | string | — | `imagetag` (AI visual) / `imagewebtag` (captions) / `imageocrmeta` (OCR) |

## License

MIT
