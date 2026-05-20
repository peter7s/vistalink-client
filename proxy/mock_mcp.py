"""Offline MCP stub. Loads handcrafted fixtures by default; faker mode for load runs."""
import json
import os
import random
import uuid
from pathlib import Path

from faker import Faker

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
fake = Faker()


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _fake_card() -> dict:
    return {
        "hotel_id": str(uuid.uuid4()),
        "name": fake.company() + " Hotel",
        "city": fake.city(),
        "country": fake.country(),
        "address": fake.street_address(),
        "star_rating": round(random.uniform(3.0, 5.0)),
        "review_score": round(random.uniform(7.0, 9.5), 1),
        "review_count": random.randint(10, 5000),
        "latitude": float(fake.latitude()),
        "longitude": float(fake.longitude()),
        "website_url": fake.url(),
        "amenities": random.sample(["wifi", "pool", "gym", "spa", "breakfast", "pet_friendly", "parking"], k=3),
        "price": None,
        "images": [
            {"url": f"https://picsum.photos/seed/{random.randint(1, 10000)}/800/600", "label": "lobby"}
            for _ in range(3)
        ],
        "review_highlight": fake.sentence(),
        "guest_insights": None,
        "description": fake.paragraph(nb_sentences=3),
        "hotel_type": random.choice(["hotel", "apartment", "boutique"]),
        "rates": None,
    }


def _mode() -> str:
    return os.getenv("VL_MOCK_MODE", "fixture")


async def search_hotels(payload: dict) -> tuple[dict, dict]:
    if _mode() == "faker":
        n = min(int(payload.get("limit", 5)), 50)
        body = {
            "hotels": [_fake_card() for _ in range(n)],
            "total": n * 10,
            "fallback_used": False,
            "fallback_message": None,
            "usage": {"latency_ms": random.randint(200, 1500), "cost_usd": 0.01},
        }
    else:
        body = _load("search_hotels.json")
    return body, _headers()


async def chat_about_hotels(payload: dict) -> tuple[dict, dict]:
    if _mode() == "faker":
        markers = " ".join(f"<!--hotel:{uuid.uuid4()}-->" for _ in range(3))
        body = {
            "session_id": payload.get("session_id") or str(uuid.uuid4()),
            "message": f"Here are a few options matching your vibe. {markers}",
            "hotels": [],
            "clarification_pending": None,
            "references": [],
            "pois": [],
            "routes": [],
            "usage": {"latency_ms": random.randint(2000, 20000), "cost_usd": 0.03},
        }
    else:
        body = _load("chat_about_hotels.json")
        body["session_id"] = payload.get("session_id") or body["session_id"]
    return body, _headers()


async def get_hotel_details(hotel_id: str, payload: dict) -> tuple[dict, dict]:
    if _mode() == "faker":
        card = _fake_card()
        card["hotel_id"] = hotel_id
        body = {
            **card,
            "phone_number": fake.phone_number(),
            "rooms": [{
                "room_name": "Standard",
                "room_size_sqm": random.randint(14, 35),
                "amenities": ["wifi", "minibar"],
                "offers": [{
                    "price": round(random.uniform(80, 400), 2),
                    "currency": "EUR",
                    "has_breakfast": random.choice([True, False]),
                    "has_free_cancellation": random.choice([True, False]),
                }],
            }],
            "reviews": [{"body": fake.sentence(), "rating": round(random.uniform(7.0, 10.0), 1)}],
            "guest_insights": {
                "highlights": random.sample(["location", "service", "design", "cleanliness", "breakfast"], k=3),
                "aspects": [{
                    "type": "service",
                    "summary": fake.sentence(),
                    "sentiment": round(random.uniform(0.6, 0.95), 2),
                    "quote": fake.sentence(),
                }],
            },
        }
    else:
        body = _load("get_hotel_details.json")
        body["hotel_id"] = hotel_id
    return body, _headers()


# In-memory tracker for simulated async call lifecycle.
# Each call_id maps to {created_at, scenario, payload}. Status is derived from time elapsed.
_CALL_REGISTRY: dict[str, dict] = {}


def _call_status_value(call_id: str) -> str:
    """Simulate progression: <2s dispatching, 2-6s in_progress, >6s completed."""
    rec = _CALL_REGISTRY.get(call_id)
    if not rec:
        return "completed"  # unknown calls return completed for offline determinism
    import time
    elapsed = time.time() - rec["created_at"]
    if elapsed < 2:
        return "dispatching"
    if elapsed < 6:
        return "in_progress"
    return "completed"


async def call_hotel(payload: dict) -> tuple[dict, dict]:
    import time
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    _CALL_REGISTRY[call_id] = {"created_at": time.time(), "scenario": payload.get("scenario", "hotel_negotiation"), "payload": payload}
    if _mode() == "faker":
        body = {
            "call_id": call_id,
            "ui_call_id": f"ui_{call_id}",
            "status": "dispatching",
            "queue_position": random.randint(1, 3),
            "message": f"Call initiated to {payload.get('hotel_name', 'the hotel')}.",
        }
    else:
        body = _load("call_hotel.json")
        body["call_id"] = call_id
        body["ui_call_id"] = f"ui_{call_id}"
    return body, _headers()


async def get_call_status(call_id: str) -> tuple[dict, dict]:
    status = _call_status_value(call_id)
    if _mode() == "faker":
        rec = _CALL_REGISTRY.get(call_id, {})
        import time
        body = {
            "call_id": call_id,
            "status": status,
            "duration_seconds": round(time.time() - rec.get("created_at", time.time()), 1) if status != "dispatching" else None,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "transcript": "Agent: Hello, this is the AI booking assistant..." if status in ("in_progress", "completed") else None,
        }
    else:
        body = _load("call_status.json")
        body["call_id"] = call_id
        body["status"] = status
    return body, _headers()


async def get_call_results(call_id: str) -> tuple[dict, dict]:
    status = _call_status_value(call_id)
    rec = _CALL_REGISTRY.get(call_id, {})
    scenario = rec.get("payload", {}).get("scenario", "hotel_negotiation")
    if status != "completed":
        # Mirror VistaLink's behavior: 409 if not ready. We return the body with status so the proxy can decide.
        return {"call_id": call_id, "status": status, "error": "not_ready", "message": "Call not complete; poll /status first."}, {**_headers(), "x-upstream-status": "409"}
    if _mode() == "faker":
        scenario_outputs = {
            "hotel_negotiation": {"negotiated_price": round(random.uniform(180, 280), 2), "currency": "EUR", "outcome": "success"},
            "hotel_confirm_booking": {"confirmation_number": f"BK{uuid.uuid4().hex[:8].upper()}", "outcome": "confirmed"},
            "hotel_cancel_booking": {"refund_amount": round(random.uniform(0, 300), 2), "currency": "EUR", "outcome": "cancelled"},
        }
        body = {
            "call_id": call_id,
            "status": "completed",
            "structured_outputs": scenario_outputs.get(scenario, {"outcome": "success"}),
            "transcript": "Agent: Hello, Hotel & Palazzo speaking...\nAI: Hello, I'm calling on behalf of...",
            "recording_url": f"https://api.vistalink.com/calls/{call_id}/recording.mp3",
            "summary": f"Scenario '{scenario}' completed successfully.",
            "duration_seconds": round(random.uniform(60, 240), 1),
            "exchange_count": random.randint(8, 20),
            "cost_usd": 0.50,
        }
    else:
        body = _load("call_results.json")
        body["call_id"] = call_id
    return body, _headers()


def _headers() -> dict:
    return {
        "x-ratelimit-remaining": str(random.randint(80, 120)),
        "x-monthly-quota-remaining": str(random.randint(900, 1000)),
        "x-ratelimit-reset": "60",
    }
