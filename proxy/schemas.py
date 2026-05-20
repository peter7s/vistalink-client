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
    """Hotel room as returned by /v1/hotels/{id}.rooms — verified live on 2026-05-20.
    NB: docs example uses `room_name`/`room_size_sqm`/`offers` but the live API
    actually returns `name`/`size_sqm`/`is_suite`/`bed_summary` with no `offers`.
    `offers` may surface when check_in_date/check_out_date query params are set.

    `images` is NOT returned by VistaLink; the proxy populates it by scanning the
    top-level `images[]` for URLs containing `/room/<room_name>/` and bucketing them
    under the matching room. See proxy/main.py:_attach_room_images."""
    room_id: Optional[str] = None
    name: Optional[str] = None
    size_sqm: Optional[float] = None
    is_suite: Optional[bool] = None
    bed_summary: Optional[str] = None
    amenities: list[str] = []
    offers: list[RoomOffer] = []
    images: list[HotelImage] = []
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


class ChatSegment(BaseModel):
    """Structured rendering chunk seen on parley.vistalink.com responses
    (not yet exposed via public /v1/chat). Alternates 'text' and 'hotel_ref'
    so clients can render inline hotel cards instead of parsing <!--hotel:UUID--> markers."""
    type: str  # "text" | "hotel_ref" (open-ended for future segment types)
    id: Optional[str] = None
    content: Optional[str] = None        # populated when type == "text"
    hotel_id: Optional[str] = None       # populated when type == "hotel_ref"
    label_preference: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class ChatResponse(BaseModel):
    """VistaLink /v1/chat. Per docs (https://vistalink.com/developers#tool-ref), `hotels`
    should contain slim candidate records like {hotel_id, name, price:{min, currency}}.
    In practice (observed 2026-05-19) it returns as []. Prose in `message` contains
    inline `<!--hotel:UUID-->` markers as a fallback signal. See docs/vistalink-chat-image-gap.md.

    Fields aliased from parley.vistalink.com's internal response shape (`hotels_core`,
    `hotel_ids`, `segments`) are included as forward-compat: VistaLink already produces
    this data internally and may expose it publicly; clients can render today if so."""
    session_id: Optional[str] = None
    message: Optional[str] = None
    hotels: list[Hotel] = []
    hotels_core: list[Hotel] = []      # alias seen on parley.vistalink.com
    hotel_ids: list[str] = []          # convenience: matches segments[].hotel_id
    segments: list[ChatSegment] = []   # structured text/hotel_ref chunks for inline rendering
    clarification_pending: Optional[Clarification] = None
    references: list[Reference] = []   # Web sources when the engine used live search
    pois: list[dict] = []              # Points of interest (shape not specified in docs)
    routes: list[dict] = []            # Route data (shape not specified in docs)
    usage: Optional[Usage] = None
    model_config = ConfigDict(extra="allow")


CallScenario = Literal["hotel_negotiation", "hotel_confirm_booking", "hotel_cancel_booking"]
CallStatusValue = Literal["dispatching", "in_progress", "completed", "failed"]


class CallRequest(BaseModel):
    """POST /v1/call body. Single endpoint dispatches to a scenario playbook.
    Pro/Enterprise tier only — free tier returns 403."""
    hotel_id: str
    phone_number: str = Field(description="E.164 format, e.g. +390551234567. Fetch from get_hotel_details.")
    hotel_name: str = Field(description="Used by the voice agent to introduce itself")
    scenario: CallScenario = "hotel_negotiation"
    guest_first_name: Optional[str] = None
    guest_last_name: Optional[str] = None
    guest_email: Optional[str] = None
    check_in_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    check_out_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    number_of_rooms: Optional[int] = Field(default=None, ge=1)
    number_of_people: Optional[int] = Field(default=None, ge=1)
    booking_price: Optional[float] = Field(default=None, ge=0)
    room_type: Optional[str] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    language: Optional[str] = Field(default=None, description="e.g. 'en', 'it', 'fr' — TTS/STT switches accordingly")
    confirmation_number: Optional[str] = None
    special_requests: Optional[str] = None
    caller_instructions: Optional[str] = Field(default=None, description="Free-form coaching for the voice agent")


class CallDispatched(BaseModel):
    """Immediate response from POST /v1/call. Returns before the call places."""
    call_id: str
    ui_call_id: Optional[str] = None
    status: CallStatusValue = "dispatching"
    queue_position: Optional[int] = None
    message: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class CallStatus(BaseModel):
    """Response from GET /v1/call/{call_id}/status. Poll every 10-30s."""
    call_id: str
    status: CallStatusValue
    duration_seconds: Optional[float] = None
    updated_at: Optional[str] = None
    transcript: Optional[str] = None  # may be partial while in_progress
    model_config = ConfigDict(extra="allow")


class CallResults(BaseModel):
    """Response from GET /v1/call/{call_id}/results.
    Returns 409 if call hasn't completed yet — poll /status first.

    Note from live testing 2026-05-20: top-level `summary` came back null and
    the real call summary lives inside structured_outputs.call_summary.
    Frontend should fall back to structured_outputs.call_summary when summary
    is null. See docs/vistalink-call-hotel-feedback.md."""
    call_id: str
    status: CallStatusValue
    structured_outputs: Optional[dict] = None  # Rich scenario-specific dict (much wider than the docs example)
    transcript: Optional[str] = None
    recording_url: Optional[str] = None        # Lives on recordings.vistalink.com, not api.vistalink.com
    summary: Optional[str] = None              # Often null; prefer structured_outputs.call_summary
    duration_seconds: Optional[float] = None
    exchange_count: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: Optional[str] = None           # ISO timestamp; not in docs but consistently returned
    completed_at: Optional[str] = None         # ISO timestamp; not in docs but consistently returned
    model_config = ConfigDict(extra="allow")


# Backwards-compat alias so existing fixture/tests still validate during migration.
CallResponse = CallDispatched
