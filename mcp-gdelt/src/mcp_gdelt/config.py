"""Configuration management for the GDELT MCP server."""

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


LogLevel = Literal["debug", "info", "warn", "error"]


@dataclass
class Config:
    gdelt_api_timeout: float = field(default_factory=lambda: float(os.getenv("GDELT_API_TIMEOUT", "30")))
    gdelt_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GDELT_API_BASE_URL", "https://api.gdeltproject.org/api/v2/doc/doc"
        )
    )
    gdelt_default_max_records: int = field(
        default_factory=lambda: int(os.getenv("GDELT_DEFAULT_MAX_RECORDS", "50"))
    )
    gdelt_default_timespan: str = field(
        default_factory=lambda: os.getenv("GDELT_DEFAULT_TIMESPAN", "1month")
    )
    gdelt_user_agent: str = field(
        default_factory=lambda: os.getenv("GDELT_USER_AGENT", "GDELT-MCP-Server/1.0")
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
