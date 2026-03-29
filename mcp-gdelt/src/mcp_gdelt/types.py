"""Pydantic models and type definitions for the GDELT APIs."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Shared enums / literals
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

# GDELT Cloud — Media Events
GDELTDetailLevel = Literal["summary", "standard", "full"]
GDELTScope       = Literal["local", "national", "global"]
GDELTQuadClass   = Literal[1, 2, 3, 4]


# ---------------------------------------------------------------------------
# DOC 2.0 API query params (internal / validated)
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
# Tool input schemas — DOC 2.0 API
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
    deduplicate: bool = Field(
        True,
        description=(
            "Remove duplicate articles (same URL) from results. "
            "GDELT returns ~20 %% duplicates from wire-service syndication. "
            "Default: True."
        ),
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
# Tool input schema — GDELT Cloud Media Events API
# ---------------------------------------------------------------------------

class SearchMediaEventsInput(BaseModel):
    """Input schema for the search_media_events tool (GDELT Cloud API).

    Requires a GDELT Cloud API key (gdelt_sk_*) set via GDELT_API_KEY.
    Data starts from January 2025 and updates hourly.
    """

    days: Optional[Annotated[int, Field(ge=1, le=30)]] = Field(
        None,
        description="Window size in days ending on `date`. days=1 returns only that date; days=7 returns 7 daily buckets. Max 30. Default: 1.",
    )
    date: Optional[str] = Field(
        None,
        description="Anchor/end date of the time window (YYYY-MM-DD). Defaults to today UTC.",
    )
    limit: Optional[Annotated[int, Field(ge=1, le=50)]] = Field(
        None,
        description="Number of clusters to return (1–50, default: 10).",
    )
    offset: Optional[Annotated[int, Field(ge=0)]] = Field(
        None,
        description="Clusters to skip for pagination (default: 0). Pass offset=10 for page 2.",
    )
    detail: Optional[GDELTDetailLevel] = Field(
        None,
        description=(
            "Response verbosity. "
            "'summary' (~120 tokens): cluster_id, label, key metrics, 3 top entities, 3 top domains — no articles. "
            "'standard' (~500 tokens): resolved metrics + 5 article cards + 10 entity cards. "
            "'full' (~1000 tokens, default): same as standard but with weight/geo on articles and wikipedia_url on entities."
        ),
    )
    search: Optional[str] = Field(
        None,
        description=(
            "Natural-language semantic search. Ranks clusters by embedding similarity instead of "
            "article count. Combinable with all other filters. "
            "Examples: 'climate change protests', 'AI regulation European Union'."
        ),
    )
    category: Optional[str] = Field(
        None,
        description=(
            "Filter by topic category. Single value or comma-separated list. "
            "Valid values: conflict_security, politics_governance, crime_justice, "
            "economy_business, science_health, disaster_emergency, society_culture, technology."
        ),
    )
    scope: Optional[GDELTScope] = Field(
        None,
        description="Filter by geographic scope: local | national | global.",
    )
    actor_country: Optional[str] = Field(
        None,
        description="CAMEO ISO-3 country code for actor1 or actor2 (e.g. USA, GBR, CHN).",
    )
    event_type: Optional[str] = Field(
        None,
        description="CAMEO event root code prefix (e.g. '14'=Protest, '18'=Assault, '19'=Fight).",
    )
    country: Optional[str] = Field(
        None,
        description=(
            "Friendly country filter. Accepts full name ('France'), ISO-3/CAMEO-3 code ('FRA'), "
            "or FIPS 2-letter code ('FR'). Note FIPS differs from ISO for some countries "
            "(Germany=GM, Russia=RS, China=CH, Japan=JA)."
        ),
    )
    location: Optional[str] = Field(
        None,
        description="Raw FIPS 10-4 two-letter country prefix (e.g. 'US', 'GM'). Prefer `country` for human input.",
    )
    language: Optional[str] = Field(
        None,
        description=(
            "Advanced filter — omit for best results. Accepts full name ('English', 'Spanish') "
            "or ISO-639-1 code ('en', 'es'). Filtering by one language significantly reduces coverage."
        ),
    )
    domain: Optional[str] = Field(
        None,
        description="Filter to clusters containing at least one article from this domain (e.g. reuters.com).",
    )
    goldstein_min: Optional[float] = Field(
        None,
        description="Minimum resolved Goldstein scale value (-10 to +10).",
    )
    goldstein_max: Optional[float] = Field(
        None,
        description="Maximum resolved Goldstein scale value (-10 to +10).",
    )
    tone_min: Optional[float] = Field(
        None,
        description="Minimum resolved average tone value (negative = more negative).",
    )
    tone_max: Optional[float] = Field(
        None,
        description="Maximum resolved average tone value.",
    )
    quad_class: Optional[GDELTQuadClass] = Field(
        None,
        description="Quad class filter: 1=Verbal Cooperation, 2=Material Cooperation, 3=Verbal Conflict, 4=Material Conflict.",
    )

    def to_request_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        for field_name, value in self.model_dump(exclude_none=True).items():
            params[field_name] = str(value)
        return params


# ---------------------------------------------------------------------------
# DOC 2.0 API response models
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


# ---------------------------------------------------------------------------
# GDELT Cloud Media Events response models
# ---------------------------------------------------------------------------

class GDELTActor(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None


class GDELTPrimaryEvent(BaseModel):
    code: Optional[str] = None
    root_code: Optional[str] = None
    description: Optional[str] = None


class GDELTPrimaryLocation(BaseModel):
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    adm1_code: Optional[str] = None
    adm1_name: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None


class GDELTTopEntity(BaseModel):
    name: Optional[str] = None
    frequency: Optional[int] = None


class GDELTResolvedMetrics(BaseModel):
    """CAMEO metrics resolved from the top-ranked non-state-linked article."""
    primary_actor1: Optional[GDELTActor] = None
    primary_actor2: Optional[GDELTActor] = None
    primary_event: Optional[GDELTPrimaryEvent] = None
    primary_location: Optional[GDELTPrimaryLocation] = None
    avg_goldstein: Optional[float] = None
    avg_tone: Optional[float] = None
    primary_quad_class: Optional[int] = None
    top_entities: Optional[list[GDELTTopEntity]] = None
    languages: Optional[list[str]] = None
    resolution_article_count: Optional[int] = None


class GDELTLinkedEntity(BaseModel):
    name: Optional[str] = None
    canonical_name: Optional[str] = None
    type: Optional[str] = None          # "person" | "organization"
    wikipedia_url: Optional[str] = None  # only present in detail=full


class GDELTArticleItem(BaseModel):
    """A representative article within a media event cluster."""
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None
    article_weight: Optional[float] = None   # quality signal; higher = more unique
    category: Optional[str] = None
    scope: Optional[str] = None
    avg_goldstein: Optional[float] = None
    avg_tone: Optional[float] = None
    quad_classes: Optional[list[int]] = None
    event_code: Optional[str] = None
    event_description: Optional[str] = None
    actor1_name: Optional[str] = None
    actor2_name: Optional[str] = None
    actor1_country_code: Optional[str] = None
    actor2_country_code: Optional[str] = None
    geo_country_name: Optional[str] = None
    geo_adm1_name: Optional[str] = None
    source_url: Optional[str] = None
    page_title: Optional[str] = None
    domain: Optional[str] = None
    article_date: Optional[str] = None
    sharing_image: Optional[str] = None
    linked_entities: Optional[list[GDELTLinkedEntity]] = None


class GDELTResolvedCluster(BaseModel):
    """A media event cluster with CAMEO metrics, articles, and linked entities."""
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None
    story_url: Optional[str] = None          # direct link to story on GDELT Cloud
    category: Optional[str] = None
    scope: Optional[GDELTScope] = None
    time_bucket: Optional[str] = None
    article_count: Optional[int] = None      # total articles in cluster
    total_events: Optional[int] = None
    resolved_metrics: Optional[GDELTResolvedMetrics] = None
    representative_articles: Optional[list[GDELTArticleItem]] = None
    linked_entities: Optional[list[GDELTLinkedEntity]] = None


class GDELTMediaEventsResponse(BaseModel):
    success: Optional[bool] = None
    clusters: Optional[list[GDELTResolvedCluster]] = None
    filters: Optional[dict] = None
    metadata: Optional[dict] = None
