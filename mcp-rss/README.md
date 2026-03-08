# mcp-rss (Python)

Python rewrite of the [mcp-rss](https://github.com/original/mcp-rss) TypeScript MCP server.
Provides 6 tools and 2 resources for fetching, parsing, monitoring, and searching RSS/Atom feeds.

## Requirements

- Python ≥ 3.11
- pip

## Installation

```bash
pip install -r requirements.txt
# or
pip install "mcp[cli]" httpx feedparser beautifulsoup4 bleach python-dotenv "pydantic>=2" pydantic-settings
```

## Running

```bash
# stdio transport (default — used by MCP clients)
python -m src.server

# or via the installed script
mcp-rss
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed. All settings can also be
provided as environment variables.

| Variable                     | Default      | Description                        |
|------------------------------|--------------|------------------------------------|
| `RSS_CACHE_TTL`              | 900000       | Cache TTL in milliseconds          |
| `RSS_MAX_ITEMS_PER_FEED`     | 100          | Max items returned per feed        |
| `RSS_REQUEST_TIMEOUT`        | 30000        | HTTP timeout in milliseconds       |
| `RSS_MAX_CONCURRENT_FETCHES` | 5            | Parallelism cap for batch fetches  |
| `RSS_USER_AGENT`             | MCP-RSS/1.0.0| HTTP User-Agent header             |
| `RSS_FOLLOW_REDIRECTS`       | true         | Follow HTTP redirects              |
| `RSS_MAX_RESPONSE_SIZE`      | 20971520     | Max response body in bytes (20 MB) |
| `RSS_CACHE_MAX_SIZE`         | 100          | Max feeds in LRU cache             |
| `RSS_CACHE_CLEANUP_INTERVAL` | 300000       | Background cleanup interval (ms)   |
| `RSS_RATE_LIMIT_PER_MINUTE`  | 60           | Max HTTP requests per minute       |
| `LOG_LEVEL`                  | info         | debug / info / warn / error        |

## Tools

| Tool                   | Description                                              |
|------------------------|----------------------------------------------------------|
| `fetch_rss_feed`       | Fetch and parse a single RSS/Atom feed                   |
| `fetch_multiple_feeds` | Batch-fetch multiple feeds (parallel or sequential)      |
| `monitor_feed_updates` | Return only items newer than a timestamp or last check   |
| `search_feed_items`    | Full-text search across one or more feeds                |
| `extract_feed_content` | Extract feed content in markdown / text / html / json    |
| `get_feed_headlines`   | Return compact headline list with title, summary, URL    |

## Resources

| URI                        | Description                           |
|----------------------------|---------------------------------------|
| `rss://cache/{feed_url}`   | Read cached feed data                 |
| `rss://opml/export`        | Export monitored feeds as OPML XML    |

## MCP client config (Claude Desktop)

```json
{
  "mcpServers": {
    "mcp-rss": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/mcp-rss-python"
    }
  }
}
```
