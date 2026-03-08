"""Structured logger that writes exclusively to stderr.

MCP uses stdout for the JSON-RPC transport, so every log line must go to
stderr to avoid corrupting the protocol stream.
"""

import sys
from datetime import datetime, timezone
from typing import Any

from .config import LogLevel, config

_LEVELS: dict[LogLevel, int] = {"debug": 0, "info": 1, "warn": 2, "error": 3}
_current_level: int = _LEVELS[config.log_level]


def _log(level: LogLevel, message: str, *args: Any) -> None:
    if _LEVELS[level] >= _current_level:
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        extra = (" " + " ".join(str(a) for a in args)) if args else ""
        print(f"[{timestamp}] [{level.upper()}] {message}{extra}", file=sys.stderr, flush=True)


class _Logger:
    def debug(self, message: str, *args: Any) -> None:
        _log("debug", message, *args)

    def info(self, message: str, *args: Any) -> None:
        _log("info", message, *args)

    def warn(self, message: str, *args: Any) -> None:
        _log("warn", message, *args)

    def error(self, message: str, *args: Any) -> None:
        _log("error", message, *args)


logger = _Logger()
