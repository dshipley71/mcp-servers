"""GDELT MCP Server — Python implementation."""

__version__ = "1.0.0"

from .services.gdelt_client import (
    GDELTAccessDeniedError,
    GDELTAuthError,
    GDELTQuotaExceededError,
    GDELTRateLimitError,
)

__all__ = ["GDELTAccessDeniedError", "GDELTAuthError", "GDELTQuotaExceededError", "GDELTRateLimitError"]
