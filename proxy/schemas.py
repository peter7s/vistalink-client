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
    url: str
    label: Optional[str] = None
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
    price: Optional[Any] = None       # Shape unconfirmed (null in test data)
    images: list[HotelImage] = []
    review_highlight: Optional[str] = None
    guest_insights: Optional[Any] = None
    description: Optional[str] = None
    hotel_type: Optional[str] = None  # e.g. "Independent"
    rates: Optional[Any] = None       # Shape unconfirmed (returned when include_rates=true)
    phone: Optional[str] = None
    rooms: list[dict] = []
    reviews: list[dict] = []
    model_config = ConfigDict(extra="allow")


# Alias: details endpoint returns the same Hotel shape (with more fields populated).
HotelDetails = Hotel


class Usage(BaseModel):
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
    model_config = ConfigDict(extra="allow")


class ChatResponse(BaseModel):
    """VistaLink /v1/chat returns prose in `message` with inline `<!--hotel:UUID-->`
    HTML comments marking each hotel. Structured `hotels` may be absent or empty.
    Frontends should parse the inline markers (or call get_hotel_details per UUID)."""
    session_id: Optional[str] = None
    message: Optional[str] = None
    hotels: list[Hotel] = []
    clarification_id: Optional[str] = None
    clarification_options: list[ClarificationOption] = []
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
