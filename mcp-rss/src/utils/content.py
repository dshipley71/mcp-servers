"""Utilities for cleaning and sanitising HTML feed content."""

from __future__ import annotations
import re
from dataclasses import dataclass

import bleach
from bs4 import BeautifulSoup

_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "a", "ul", "ol", "li",
    "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
]
_ALLOWED_ATTRS = {"a": ["href", "title"]}


@dataclass
class CleanedContent:
    text: str
    html: str


_REMOVE_TAGS = {"script", "style", "noscript", "iframe", "object", "embed"}


def extract_clean_content(html: str) -> CleanedContent:
    """Strip dangerous HTML and extract plain text from feed content.

    Matches the behaviour of the original DOMPurify-based TypeScript implementation:
    dangerous tags (and their inner text) are removed entirely before the
    remaining markup is sanitised down to the allowed-tag set.
    """
    try:
        # 1. Parse and surgically remove dangerous tags + their content.
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()
        pre_cleaned = str(soup)

        # 2. Allowlist-sanitise the remaining HTML.
        clean_html = bleach.clean(
            pre_cleaned,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRS,
            strip=True,
        )

        # 3. Extract plain text.
        text_soup = BeautifulSoup(clean_html, "html.parser")
        text = text_soup.get_text(separator=" ")
        text = re.sub(r"\s+", " ", text).strip()
        return CleanedContent(text=text, html=clean_html)
    except Exception:
        # Fallback: strip all tags manually
        raw_text = re.sub(r"<[^>]*>", "", html)
        raw_text = re.sub(r"\s+", " ", raw_text).strip()
        return CleanedContent(text=raw_text, html=html)


def sanitize_string(value: str) -> str:
    """Convert an arbitrary string into a safe identifier."""
    if not value:
        return ""
    result = value.lower()
    result = re.sub(r"[^a-z0-9]+", "-", result)
    result = result.strip("-")
    return result
