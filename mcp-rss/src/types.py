"""Core data types for the MCP-RSS server."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Enclosure:
    url: str
    type: Optional[str] = None
    length: Optional[int] = None


@dataclass
class FeedItem:
    id: str
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    published: Optional[int] = None   # epoch milliseconds
    updated: Optional[int] = None     # epoch milliseconds
    author: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    enclosures: list[Enclosure] = field(default_factory=list)
    guid: Optional[str] = None


@dataclass
class FeedImage:
    url: Optional[str] = None
    title: Optional[str] = None


@dataclass
class FeedInfo:
    feed_url: str
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    language: Optional[str] = None
    copyright: Optional[str] = None
    published: Optional[int] = None   # epoch milliseconds
    updated: Optional[int] = None     # epoch milliseconds
    categories: list[str] = field(default_factory=list)
    author: Optional[str] = None
    image: Optional[FeedImage] = None


@dataclass
class FeedResult:
    info: FeedInfo
    items: list[FeedItem]
    fetched_at: int                   # epoch milliseconds
    etag: Optional[str] = None
    last_modified: Optional[str] = None


@dataclass
class FeedError:
    url: str
    error: str
    code: Optional[str] = None
    timestamp: int = 0


@dataclass
class MultiFeedResult:
    url: str
    success: bool
    data: Optional[FeedResult] = None
    error: Optional[FeedError] = None


@dataclass
class CacheEntry:
    data: FeedResult
    expires_at: int
    etag: Optional[str] = None
    last_modified: Optional[str] = None
