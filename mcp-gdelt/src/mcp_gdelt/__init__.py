"""GDELT MCP Server — Python implementation."""

__version__ = "1.0.0"

from .services.gdelt_client import GDELTQuotaExceededError

__all__ = ["GDELTQuotaExceededError"]
