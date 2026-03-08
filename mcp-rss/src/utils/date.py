"""Date/time helpers for converting feed timestamps to epoch milliseconds."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Union
import time


def to_epoch_ms(value: Union[str, datetime, None]) -> int | None:
    """Convert a date string or datetime object to epoch milliseconds."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, str):
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
    return None


def now_ms() -> int:
    """Current time as epoch milliseconds."""
    return int(time.time() * 1000)
