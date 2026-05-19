"""Frontend contract. Every VistaLink response must validate against these.

Two groups of models:
- Request models (SearchRequest, ChatRequest) — what we accept inbound, mirroring the
  real /v1/search and /v1/chat parameter surfaces from the VistaLink docs.
- Response models (Hotel, SearchResponse, ChatResponse, HotelDetails, CallResponse) —
  what a frontend needs to render. Aligned with the real /v1/* response shapes after
  the first live smoke test on 2026-05-18.

All response models use `extra="allow"` so we tolerate field additions from VistaLink
without breaking — but missing REQUIRED fields will still fail validation.
"""
from typing import Optional, Literal, Any
from pydantic import BaseModel, ConfigDict, Field


# ─── Request models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Mirror of POST /v1/search parameters. All optional; send only what you have."""
    city: Optional[str] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_meters: Optional[int] = Field(default=None, ge=0)
    check_in: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    check_out: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    guests: Optional[int] = Field(default=None, ge=1)
    rooms: Optional[int] = Field(default=None, ge=1)
    budget_min: Optional[float] = Field(default=None, ge=0)
    budget_max: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    amenities: Optional[str] = Field(default=None, description="Comma-separated, e.g. 'wifi,pool,spa'")
    vibe: Optional[str] = Field(default=None, description="Comma-separated, e.g. 'romantic,quiet'")
    hotel_name: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=50)
    include_rates: bool = False


class ChatRequest(BaseModel):
    """Mirror of POST /v1/chat parameters."""
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None
    guest_id: Optional[str] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    locale: Optional[str] = Field(default=None, description="e.g. 'en-GB', 'it-IT'")
    context: Optional[dict[str, Any]] = Field(default=None, description="Free-form guest context")
    clarification_id: Optional[str] = None
    clarification_option_id: Optional[str] = None


# ─── Response models ───────────────────────────────────────────────────────────

class HotelImage(BaseModel):
    """Image object — field names differ between endpoints:
    - /v1/search responses: {url, label}
    - /v1/hotels/{id} responses (per docs): {url, category, caption}
    We accept all variants. Frontends should prefer caption || label || category for alt text."""
    url: str
    label: Optional[str] = None      # seen on /v1/search
    category: Optional[str] = None   # docs for /v1/hotels/{id}
    caption: Optional[str] = None    # docs for /v1/hotels/{id}
    model_config = ConfigDict(extra="allow")


class Price(BaseModel):
    """Slim price object seen on chat-response hotels: {min, currency}."""
    min: Optional[float] = None
    max: Optional[float] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    per: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class RoomOffer(BaseModel):
    price: Optional[float] = None
    currency: Optional[str] = None
    has_breakfast: Optional[bool] = None
    has_free_cancellation: Optional[bool] = None
    model_config = ConfigDict(extra="allow")


class Room(BaseModel):
    """Hotel room as returned by /v1/hotels/{id}.rooms."""
    room_name: Optional[str] = None
    room_size_sqm: Optional[float] = None
    amenities: list[str] = []
    offers: list[RoomOffer] = []
    model_config = ConfigDict(extra="allow")


class Review(BaseModel):
    """Hotel review as returned by /v1/hotels/{id}.reviews."""
    body: Optional[str] = None
    rating: Optional[float] = None
    model_config = ConfigDict(extra="allow")


class GuestInsightAspect(BaseModel):
    type: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[float] = None
    quote: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class GuestInsights(BaseModel):
    highlights: list[str] = []
    aspects: list[GuestInsightAspect] = []
    model_config = ConfigDict(extra="allow")


class Hotel(BaseModel):
    """Single hotel as returned by /v1/search and /v1/hotels/{id}.
    Same shape for both endpoints; details just populates more nullable fields."""
    hotel_id: str
    name: str
    city: Optional[str] = None
    country: Optional[str] = None  # Full name ("France"), not ISO code
    address: Optional[str] = None
    star_rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_score: Optional[float] = Field(default=None, ge=0, le=10)
    review_count: Optional[int] = Field(default=None, ge=0)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    website_url: Optional[str] = None
    amenities: list[str] = []
    price: Optional[Price] = None     # Slim {min, currency} on chat hotels; usually null on search
    images: list[HotelImage] = []
    review_highlight: Optional[str] = None
    guest_insights: Optional[GuestInsights] = None
    description: Optional[str] = None
    hotel_type: Optional[str] = None  # e.g. "Independent", "hotel"
    rates: Optional[Any] = None       # Shape unconfirmed (returned when include_rates=true)
    phone_number: Optional[str] = None  # Per docs — mandatory before any call_hotel request
    rooms: list[Room] = []
    reviews: list[Review] = []
    model_config = ConfigDict(extra="allow")


# Alias: details endpoint returns the same Hotel shape (with more fields populated).
HotelDetails = Hotel


class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    model_config = ConfigDict(extra="allow")


class SearchResponse(BaseModel):
    hotels: list[Hotel] = []
    total: int = 0
    fallback_used: bool = False
    fallback_message: Optional[str] = None
    usage: Optional[Usage] = None
    model_config = ConfigDict(extra="allow")


class ClarificationOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class Clarification(BaseModel):
    """Nested clarification object as documented: ChatResponse.clarification_pending."""
    clarification_id: str
    question: str
    options: list[ClarificationOption] = []
    context_hint: Optional[str] = None   # Per docs — extra context on why clarification is needed
    allow_free_text: bool = False
    display_mode: Optional[str] = None   # e.g. "inline"
    model_config = ConfigDict(extra="allow")


class Reference(BaseModel):
    """Web source returned in chat.references when the engine ran web search."""
    url: str
    title: Optional[str] = None
    domain: Optional[str] = None
    index: Optional[int] = None
    model_config = ConfigDict(extra="allow")


class ChatResponse(BaseModel):
    """VistaLink /v1/chat. Per docs (https://vistalink.com/developers#tool-ref), `hotels`
    should contain slim candidate records like {hotel_id, name, price:{min, currency}}.
    In practice (observed 2026-05-19) it returns as []. Prose in `message` contains
    inline `<!--hotel:UUID-->` markers as a fallback signal. See docs/vistalink-chat-image-gap.md."""
    session_id: Optional[str] = None
    message: Optional[str] = None
    hotels: list[Hotel] = []
    clarification_pending: Optional[Clarification] = None
    references: list[Reference] = []   # Web sources when the engine used live search
    pois: list[dict] = []              # Points of interest (shape not specified in docs)
    routes: list[dict] = []            # Route data (shape not specified in docs)
    usage: Optional[Usage] = None
    model_config = ConfigDict(extra="allow")


class CallResponse(BaseModel):
    """Legacy single-call shape. Voice flow refactor pending — see proxy/mcp_client.py."""
    call_id: str
    status: Literal["queued", "in_progress", "completed", "failed"]
    transcript_url: Optional[str] = None
    summary: Optional[str] = None
    duration_seconds: Optional[float] = None
    model_config = ConfigDict(extra="allow")
