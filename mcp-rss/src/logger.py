"""Structured logger that writes to stderr (stdio-safe for MCP)."""

from __future__ import annotations
import sys
import logging
from datetime import datetime, timezone

from .config import config

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


class _StderrHandler(logging.StreamHandler):
    def __init__(self) -> None:
        super().__init__(sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        level = record.levelname.upper()
        msg = self.format(record)
        print(f"[{ts}] [{level}] {msg}", file=sys.stderr, flush=True)


def _build_logger() -> logging.Logger:
    log = logging.getLogger("mcp-rss")
    log.setLevel(_LEVEL_MAP.get(config.log_level, logging.INFO))
    if not log.handlers:
        handler = _StderrHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
    return log


logger = _build_logger()
