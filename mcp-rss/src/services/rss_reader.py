"""RSS / Atom feed fetching and parsing service."""

from __future__ import annotations
import uuid
from typing import Optional

import feedparser

from ..config import config
from ..logger import logger
from ..types import (
    Enclosure,
    FeedImage,
    FeedInfo,
    FeedItem,
    FeedResult,
)
from ..utils.content import extract_clean_content, sanitize_string
from ..utils.date import now_ms, to_epoch_ms
from ..utils.http import http_client


class RSSReader:
    # ------------------------------------------------------------------
    # Raw fetch
    # ------------------------------------------------------------------

    async def fetch_raw_feed(
        self,
        url: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> dict:
        """Download the raw feed XML, honouring conditional GET headers."""
        logger.debug(f"Fetching RSS feed from: {url}")

        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            response = await http_client.get(url, headers=headers)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch RSS feed: {exc}") from exc

        if response.status_code == 304:
            logger.debug(f"Feed not modified: {url}")
            return {
                "data": "",
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "not_modified": True,
            }

        if response.status_code >= 400:
            raise RuntimeError(
                f"HTTP {response.status_code} fetching feed: {url}"
            )

        content = response.text
        if len(content.encode()) > config.rss_max_response_size:
            raise RuntimeError("Feed response exceeds maximum allowed size")

        return {
            "data": content,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "not_modified": False,
        }

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_feed(self, xml: str) -> Optional[feedparser.FeedParserDict]:
        """Parse raw XML/Atom/RSS into a feedparser dict."""
        try:
            parsed = feedparser.parse(xml)
            if parsed.get("bozo") and not parsed.get("entries"):
                logger.error(
                    f"Feed parse error: {parsed.get('bozo_exception')}"
                )
                return None
            return parsed
        except Exception as exc:
            logger.error(f"Error parsing RSS feed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_feed(
        self,
        parsed: feedparser.FeedParserDict,
        feed_url: str,
        use_description_as_content: bool = False,
    ) -> FeedResult:
        """Convert a feedparser dict into our internal FeedResult."""
        feed_meta = parsed.feed

        # ---- Feed-level info ----------------------------------------
        image_obj = getattr(feed_meta, "image", None)
        image = (
            FeedImage(
                url=getattr(image_obj, "href", None),
                title=getattr(image_obj, "title", None),
            )
            if image_obj
            else None
        )

        # Author may be a string or a list of author dicts
        author = _first_author(feed_meta)

        # Categories may be strings or tag dicts
        categories = _extract_categories(
            getattr(feed_meta, "tags", [])
            or getattr(feed_meta, "categories", [])
        )

        info = FeedInfo(
            feed_url=feed_url,
            title=getattr(feed_meta, "title", None) or None,
            description=(
                getattr(feed_meta, "subtitle", None)
                or getattr(feed_meta, "description", None)
                or None
            ),
            url=getattr(feed_meta, "link", None) or None,
            language=getattr(feed_meta, "language", None) or None,
            copyright=(
                getattr(feed_meta, "rights", None)
                or getattr(feed_meta, "copyright", None)
                or None
            ),
            published=to_epoch_ms(
                getattr(feed_meta, "published", None)
                or getattr(feed_meta, "updated", None)
            ),
            updated=to_epoch_ms(getattr(feed_meta, "updated", None)),
            categories=categories,
            author=author,
            image=image,
        )

        # ---- Items --------------------------------------------------
        items: list[FeedItem] = []
        for entry in parsed.entries[: config.rss_max_items_per_feed]:
            items.append(
                self._format_item(entry, use_description_as_content)
            )

        return FeedResult(
            info=info,
            items=items,
            fetched_at=now_ms(),
        )

    def _format_item(
        self,
        entry: feedparser.FeedParserDict,
        use_description_as_content: bool,
    ) -> FeedItem:
        # Raw content / description
        raw_content: Optional[str] = None
        if hasattr(entry, "content") and entry.content:
            raw_content = entry.content[0].get("value")
        raw_description: Optional[str] = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
        )

        # Clean both fields
        content = (
            extract_clean_content(raw_content).text if raw_content else None
        )
        description = (
            extract_clean_content(raw_description).text
            if raw_description
            else None
        )

        if use_description_as_content and description:
            content = description

        # GUID / ID
        guid: str = (
            getattr(entry, "id", None)
            or getattr(entry, "guid", None)
            or str(uuid.uuid4())
        )

        # Enclosures
        enclosures = [
            Enclosure(
                url=enc.get("url", ""),
                type=enc.get("type"),
                length=(
                    int(enc["length"])
                    if enc.get("length") and str(enc["length"]).isdigit()
                    else None
                ),
            )
            for enc in getattr(entry, "enclosures", [])
        ]

        item_url = getattr(entry, "link", None) or None
        item_title = getattr(entry, "title", None) or None

        return FeedItem(
            id=sanitize_string(guid or item_url or item_title or ""),
            title=item_title,
            url=item_url,
            content=content,
            description=description,
            published=to_epoch_ms(
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
            ),
            updated=to_epoch_ms(getattr(entry, "updated", None)),
            author=_first_author(entry),
            categories=_extract_categories(
                getattr(entry, "tags", [])
                or getattr(entry, "categories", [])
            ),
            enclosures=enclosures,
            guid=guid,
        )

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def fetch_feed(
        self,
        url: str,
        *,
        use_description_as_content: bool = False,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> FeedResult:
        raw = await self.fetch_raw_feed(url, etag=etag, last_modified=last_modified)

        if raw["not_modified"]:
            raise RuntimeError("NOT_MODIFIED")

        parsed = self.parse_feed(raw["data"])
        if parsed is None:
            raise RuntimeError("Failed to parse feed XML")

        result = self.format_feed(parsed, url, use_description_as_content)

        if raw.get("etag"):
            result.etag = raw["etag"]
        if raw.get("last_modified"):
            result.last_modified = raw["last_modified"]

        return result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _first_author(obj) -> Optional[str]:
    """Extract author name from a feedparser feed or entry object."""
    name = getattr(obj, "author", None)
    if name:
        return name
    authors = getattr(obj, "authors", None)
    if authors and isinstance(authors, list):
        return authors[0].get("name") if isinstance(authors[0], dict) else None
    return None


def _extract_categories(tags) -> list[str]:
    result = []
    for tag in tags:
        if isinstance(tag, str):
            result.append(tag)
        elif isinstance(tag, dict):
            label = tag.get("label") or tag.get("term") or tag.get("scheme")
            if label:
                result.append(label)
        else:
            term = getattr(tag, "label", None) or getattr(tag, "term", None)
            if term:
                result.append(term)
    return result


# Module-level singleton
rss_reader = RSSReader()
