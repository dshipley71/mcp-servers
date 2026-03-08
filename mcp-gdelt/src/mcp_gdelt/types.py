"""Pydantic models and type definitions for the GDELT DOC 2.0 API."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums / literals
# ---------------------------------------------------------------------------

GDELTMode = Literal[
    "ArtList",
    "ArtGallery",
    "TimelineVol",
    "TimelineVolInfo",
    "TimelineTone",
    "TimelineSourceCountry",
    "ToneChart",
    "WordCloud",
    "ImageCollage",
    "ImageCollageInfo",
    "ImageGallery",
]

GDELTFormat = Literal["JSON", "HTML", "RSS", "RSSArchive"]

GDELTSort = Literal["DateDesc", "DateAsc", "ToneAsc", "ToneDesc", "HybridRel"]

ImageType = Literal["imagetag", "imagewebtag", "imageocrmeta"]


# ---------------------------------------------------------------------------
# GDELT API query params (internal / validated)
# ---------------------------------------------------------------------------

class GDELTQueryParams(BaseModel):
    """Validated parameters sent to the GDELT DOC 2.0 API."""

    query: str = Field(..., min_length=1)
    mode: GDELTMode = "ArtList"
    format: GDELTFormat = "JSON"
    maxrecords: Annotated[int, Field(ge=1, le=250)] = 50
    sort: GDELTSort = "DateDesc"
    timespan: str = "1month"
    startdatetime: Optional[str] = None
    enddatetime: Optional[str] = None

    @field_validator("startdatetime", "enddatetime", mode="before")
    @classmethod
    def validate_datetime_fmt(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 14:
            raise ValueError("datetime must be in YYYYMMDDHHMMSS format (14 chars)")
        return v

    def to_request_params(self) -> dict[str, str]:
        """Serialize to the flat string dict expected by the GDELT HTTP API."""
        params: dict[str, str] = {
            "query": self.query,
            "mode": self.mode,
            "format": self.format,
            "maxrecords": str(self.maxrecords),
            "sort": self.sort,
        }
        if self.timespan:
            params["timespan"] = self.timespan
        if self.startdatetime:
            params["startdatetime"] = self.startdatetime
        if self.enddatetime:
            params["enddatetime"] = self.enddatetime
        return params


# ---------------------------------------------------------------------------
# Tool input schemas (exposed to MCP clients)
# ---------------------------------------------------------------------------

class SearchArticlesInput(BaseModel):
    """Input schema for the search_articles tool."""

    query: str = Field(
        ...,
        description=(
            "Search query. Supports keywords, exact phrases in quotes, "
            "and Boolean operators OR / AND."
        ),
    )
    max_records: Optional[Annotated[int, Field(ge=1, le=250)]] = Field(
        None,
        description="Maximum number of articles to return (1–250, default: 50).",
    )
    timespan: Optional[str] = Field(
        None,
        description='Time period to search, e.g. "1month", "7d", "24h" (default: "1month").',
    )
    sort: Optional[GDELTSort] = Field(
        None,
        description="Sort order (default: DateDesc).",
    )
    start_date_time: Optional[str] = Field(
        None,
        description="Start date in YYYYMMDDHHMMSS format.",
    )
    end_date_time: Optional[str] = Field(
        None,
        description="End date in YYYYMMDDHHMMSS format.",
    )


class SearchImagesInput(BaseModel):
    """Input schema for the search_images tool."""

    query: str = Field(..., description="Search term for images (e.g. 'fire', 'protest', 'flood').")
    max_records: Optional[Annotated[int, Field(ge=1, le=250)]] = Field(
        None,
        description="Maximum number of images to return (1–250, default: 50).",
    )
    timespan: Optional[str] = Field(
        None,
        description='Time period to search (default: "1month").',
    )
    image_type: Optional[ImageType] = Field(
        None,
        description=(
            "Image search type: "
            "'imagetag' (visual AI content), "
            "'imagewebtag' (caption / context), "
            "'imageocrmeta' (OCR + metadata). "
            "Default: 'imagetag'."
        ),
    )


# ---------------------------------------------------------------------------
# GDELT API response models
# ---------------------------------------------------------------------------

class GDELTArticle(BaseModel):
    url: str
    url_mobile: Optional[str] = None
    title: str
    seendate: str
    socialimage: Optional[str] = None
    domain: str
    language: str
    sourcecountry: str


class GDELTImage(BaseModel):
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None
    format: Optional[str] = None


class GDELTAPIResponse(BaseModel):
    articles: Optional[list[GDELTArticle]] = None
    images: Optional[list[GDELTImage]] = None
