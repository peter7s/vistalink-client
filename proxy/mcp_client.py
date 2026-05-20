"""Real VistaLink REST client. Endpoint paths follow https://vistalink.com/developers (/v1/*).

NOTE: voice/call surface is intentionally NOT yet updated to the new scenario-specific
endpoints (/v1/hotel/negotiate, /v1/hotel/confirm-booking, /v1/hotel/cancel-booking,
/v1/hotel/callback) and the async status/results polling. call_hotel below will 404
against the live API; use mock mode for any voice testing until that refactor lands.
"""
import os
import httpx

BASE = os.getenv("VL_API_BASE", "https://api.vistalink.com")
KEY = os.getenv("VL_API_KEY", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def _safe_parse(r: httpx.Response) -> dict:
    """Return JSON body, or a structured error dict if the response isn't JSON.
    Prevents the proxy from 500-ing when VistaLink returns an HTML error page."""
    try:
        return r.json()
    except ValueError:
        return {"error": {"status_code": r.status_code, "body_preview": r.text[:500]}}


async def search_hotels(payload: dict) -> tuple[dict, dict]:
    return await _post("/v1/search", payload)


async def chat_about_hotels(payload: dict) -> tuple[dict, dict]:
    return await _post("/v1/chat", payload)


async def get_hotel_details(hotel_id: str, payload: dict) -> tuple[dict, dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/v1/hotels/{hotel_id}", params=payload, headers=_headers())
    headers = dict(r.headers) | {"x-upstream-status": str(r.status_code)}
    return _safe_parse(r), headers


# Voice call surface — single dispatcher + async polling lifecycle.
# Pro/Enterprise tier only; free-tier keys get HTTP 403.
async def call_hotel(payload: dict) -> tuple[dict, dict]:
    return await _post("/v1/call", payload)


async def get_call_status(call_id: str) -> tuple[dict, dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/v1/call/{call_id}/status", headers=_headers())
    headers = dict(r.headers) | {"x-upstream-status": str(r.status_code)}
    return _safe_parse(r), headers


async def get_call_results(call_id: str) -> tuple[dict, dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/v1/call/{call_id}/results", headers=_headers())
    headers = dict(r.headers) | {"x-upstream-status": str(r.status_code)}
    return _safe_parse(r), headers


async def _post(path: str, payload: dict) -> tuple[dict, dict]:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}{path}", json=payload, headers=_headers())
    headers = dict(r.headers) | {"x-upstream-status": str(r.status_code)}
    return _safe_parse(r), headers
