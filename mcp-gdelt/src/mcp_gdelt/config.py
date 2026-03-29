"""Configuration management for the GDELT MCP server."""

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


LogLevel = Literal["debug", "info", "warn", "error"]

# Rate-limit intervals differ between anonymous and authenticated access.
# Anonymous (no key): GDELT enforces ~1 request per 5 seconds.
# Authenticated (API key): higher throughput; 1 second is a safe default.
_ANON_RATE_LIMIT = 6.0   # seconds — buffer above the stated 5 s limit
_AUTH_RATE_LIMIT = 1.0   # seconds — conservative default for keyed access


@dataclass
class Config:
    gdelt_api_key: str = field(
        default_factory=lambda: os.getenv("GDELT_API_KEY", "")
    )
    # ── Granular timeouts (py-gdelt pattern) ──────────────────────────────
    # read_timeout replaces the old flat gdelt_api_timeout.
    # connect/write/pool are short because only the actual data transfer is slow.
    gdelt_connect_timeout: float = field(
        default_factory=lambda: float(os.getenv("GDELT_CONNECT_TIMEOUT", "10.0"))
    )
    gdelt_read_timeout: float = field(
        default_factory=lambda: float(os.getenv("GDELT_API_TIMEOUT", "60.0"))
    )
    gdelt_write_timeout: float = field(
        default_factory=lambda: float(os.getenv("GDELT_WRITE_TIMEOUT", "10.0"))
    )
    gdelt_pool_timeout: float = field(
        default_factory=lambda: float(os.getenv("GDELT_POOL_TIMEOUT", "5.0"))
    )
    # ── Connection pool limits (py-gdelt pattern) ─────────────────────────
    gdelt_max_keepalive_connections: int = field(
        default_factory=lambda: int(os.getenv("GDELT_MAX_KEEPALIVE_CONNECTIONS", "20"))
    )
    gdelt_max_connections: int = field(
        default_factory=lambda: int(os.getenv("GDELT_MAX_CONNECTIONS", "100"))
    )
    gdelt_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GDELT_API_BASE_URL", "https://api.gdeltproject.org/api/v2/doc/doc"
        )
    )
    gdelt_cloud_base_url: str = field(
        default_factory=lambda: os.getenv("GDELT_CLOUD_BASE_URL", "https://gdeltcloud.com")
    )
    gdelt_default_max_records: int = field(
        default_factory=lambda: int(os.getenv("GDELT_DEFAULT_MAX_RECORDS", "50"))
    )
    gdelt_default_timespan: str = field(
        default_factory=lambda: os.getenv("GDELT_DEFAULT_TIMESPAN", "1month")
    )
    gdelt_user_agent: str = field(
        default_factory=lambda: os.getenv(
            "GDELT_USER_AGENT",
            "Mozilla/5.0 (compatible; mcp-gdelt/1.0; +https://github.com/dshipley71/mcp-servers)",
        )
    )
    gdelt_rate_limit_interval: float = field(
        default_factory=lambda: float(
            os.getenv(
                "GDELT_RATE_LIMIT_INTERVAL",
                str(_AUTH_RATE_LIMIT if os.getenv("GDELT_API_KEY") else _ANON_RATE_LIMIT),
            )
        )
    )
    gdelt_max_retries: int = field(
        default_factory=lambda: int(os.getenv("GDELT_MAX_RETRIES", "4"))
    )
    gdelt_retry_base_wait: float = field(
        default_factory=lambda: float(os.getenv("GDELT_RETRY_BASE_WAIT", "6.0"))
    )
    gdelt_retry_rate_limit_wait: float = field(
        default_factory=lambda: float(os.getenv("GDELT_RETRY_RATE_LIMIT_WAIT", "60.0"))
    )
    gdelt_cache_ttl: float = field(
        default_factory=lambda: float(os.getenv("GDELT_CACHE_TTL", "300.0"))
    )
    # ── Tiered TTL: historical queries (fixed past window) are cached much
    # longer because the underlying data never changes.  A query is treated
    # as historical when BOTH startdatetime and enddatetime are present and
    # the window ended more than gdelt_historical_threshold_days ago.
    # Set gdelt_historical_cache_ttl=0 to use the standard TTL for everything.
    gdelt_historical_cache_ttl: float = field(
        default_factory=lambda: float(os.getenv("GDELT_HISTORICAL_CACHE_TTL", "86400.0"))  # 24 h
    )
    gdelt_historical_threshold_days: int = field(
        default_factory=lambda: int(os.getenv("GDELT_HISTORICAL_THRESHOLD_DAYS", "30"))
    )
    # ── Retry jitter ──────────────────────────────────────────────────────
    # Adds a random fraction of the base wait to spread concurrent clients.
    # 0.25 means up to +25 % of the computed wait is added at random.
    gdelt_retry_jitter: float = field(
        default_factory=lambda: float(os.getenv("GDELT_RETRY_JITTER", "0.25"))
    )
    log_level: LogLevel = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "info")  # type: ignore[return-value]
    )

    def __post_init__(self) -> None:
        if not 1 <= self.gdelt_default_max_records <= 250:
            raise ValueError("GDELT_DEFAULT_MAX_RECORDS must be between 1 and 250")
        if self.log_level not in ("debug", "info", "warn", "error"):
            raise ValueError(f"Invalid LOG_LEVEL: {self.log_level}")


config = Config()
