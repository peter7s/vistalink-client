"""MCP server: exposes the four VistaLink tools over the MCP protocol (JSON-RPC over stdio).
Run this so Claude Desktop / Claude Code can register VistaLink as an MCP server.

Same backend (mock or live) as the FastAPI proxy — only the transport differs.

Run:
    VL_MODE=mock python -m proxy.mcp_server
"""
import os

from mcp.server.fastmcp import FastMCP

from proxy import metrics, schemas

MODE = os.getenv("VL_MODE", "mock")
if MODE == "live":
    from proxy import mcp_client as backend
else:
    from proxy import mock_mcp as backend

mcp = FastMCP("vistalink")


def _record(tool: str, request: dict, body: dict, headers: dict, model):
    """Mirror of the per-call bookkeeping in proxy/main.py so both transports log identically."""
    with metrics.record(tool, request) as row:
        row["status_code"] = 200
        row["rate_limit_remaining"] = headers.get("x-ratelimit-remaining")
        row["monthly_quota_remaining"] = headers.get("x-monthly-quota-remaining")
        valid, missing = metrics.validate(body, model)
        row["schema_valid"] = valid
        row["missing_fields"] = missing
        if tool == "call_hotel":
            row["duration_seconds"] = body.get("duration_seconds", 0)


@mcp.tool()
async def search_hotels(
    city: str = "",
    country: str = "",
    check_in: str = "",
    check_out: str = "",
    guests: int = 0,
    rooms: int = 0,
    budget_min: float = 0.0,
    budget_max: float = 0.0,
    currency: str = "",
    amenities: str = "",
    vibe: str = "",
    hotel_name: str = "",
    limit: int = 20,
    include_rates: bool = False,
) -> dict:
    """Structured hotel search. amenities/vibe are comma-separated; dates are YYYY-MM-DD."""
    payload: dict = {"limit": limit, "include_rates": include_rates}
    for k, v in {"city": city, "country": country, "check_in": check_in, "check_out": check_out,
                 "currency": currency, "amenities": amenities, "vibe": vibe, "hotel_name": hotel_name}.items():
        if v:
            payload[k] = v
    for k, v in {"guests": guests, "rooms": rooms, "budget_min": budget_min, "budget_max": budget_max}.items():
        if v:
            payload[k] = v
    body, headers = await backend.search_hotels(payload)
    _record("search_hotels", payload, body, headers, schemas.SearchResponse)
    return body


@mcp.tool()
async def chat_about_hotels(
    message: str,
    session_id: str = "",
    guest_id: str = "",
    currency: str = "",
    locale: str = "",
    clarification_id: str = "",
    clarification_option_id: str = "",
) -> dict:
    """Conversational hotel search. Pass session_id to continue a prior conversation."""
    payload: dict = {"message": message}
    for k, v in {"session_id": session_id, "guest_id": guest_id, "currency": currency, "locale": locale,
                 "clarification_id": clarification_id, "clarification_option_id": clarification_option_id}.items():
        if v:
            payload[k] = v
    body, headers = await backend.chat_about_hotels(payload)
    _record("chat_about_hotels", payload, body, headers, schemas.ChatResponse)
    return body


@mcp.tool()
async def get_hotel_details(hotel_id: str, currency: str = "") -> dict:
    """Get the full record for one hotel: description, images, rooms, reviews, phone."""
    payload: dict = {"currency": currency} if currency else {}
    body, headers = await backend.get_hotel_details(hotel_id, payload)
    _record("get_hotel_details", {"hotel_id": hotel_id, **payload}, body, headers, schemas.HotelDetails)
    return body


@mcp.tool()
async def call_hotel(hotel_id: str, instructions: str = "ask about availability") -> dict:
    """Trigger an AI voice call to a hotel to negotiate or ask questions."""
    payload = {"hotel_id": hotel_id, "instructions": instructions}
    body, headers = await backend.call_hotel(payload)
    _record("call_hotel", payload, body, headers, schemas.CallResponse)
    return body


if __name__ == "__main__":
    mcp.run()
