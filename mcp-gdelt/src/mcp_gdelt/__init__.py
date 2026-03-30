"""GDELT MCP Server — Python implementation."""

__version__ = "1.0.0"

from .services.gdelt_client import (
    GDELTAccessDeniedError,
    GDELTAuthError,
    GDELTClientError,
    GDELTParseError,
    GDELTQuotaExceededError,
    GDELTRateLimitError,
    GDELTServerError,
)

__all__ = [
    "GDELTAccessDeniedError",
    "GDELTAuthError",
    "GDELTClientError",
    "GDELTParseError",
    "GDELTQuotaExceededError",
    "GDELTRateLimitError",
    "GDELTServerError",
]
