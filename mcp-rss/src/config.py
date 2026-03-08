"""Configuration loaded from environment variables with typed defaults."""

from __future__ import annotations
import os
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    # Cache settings
    rss_cache_ttl: int = 900_000               # 15 minutes in ms
    rss_max_items_per_feed: int = 100

    # HTTP settings
    rss_request_timeout: int = 30_000          # 30 seconds in ms
    rss_max_concurrent_fetches: int = 5
    rss_user_agent: str = "MCP-RSS/1.0.0"
    rss_follow_redirects: bool = True
    rss_max_response_size: int = 20 * 1024 * 1024  # 20 MB

    # Storage settings
    rss_storage_path: str | None = None
    rss_enable_persistence: bool = False

    # Cache management
    rss_cache_max_size: int = 100
    rss_cache_cleanup_interval: int = 300_000  # 5 minutes in ms

    # Rate limiting
    rss_rate_limit_per_minute: int = 60

    # Logging
    log_level: str = "info"

    model_config = {"env_prefix": "", "case_sensitive": False}

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warn", "error"}
        if v.lower() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.lower()


config = Config()
