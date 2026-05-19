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
        "hotel_type": random.choice(["Independent", "Chain", "Boutique"]),
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
            "rooms": [{"name": "Standard", "description": fake.sentence()}],
            "reviews": [{"author": fake.name(), "rating": 5, "text": fake.sentence()}],
        }
    else:
        body = _load("get_hotel_details.json")
        body["hotel_id"] = hotel_id
    return body, _headers()


async def call_hotel(payload: dict) -> tuple[dict, dict]:
    if _mode() == "faker":
        body = {
            "call_id": uuid.uuid4().hex,
            "status": "completed",
            "transcript_url": f"https://api.vistalink.com/calls/{uuid.uuid4().hex}/transcript",
            "summary": "Negotiated 12% off; late checkout confirmed.",
            "duration_seconds": round(random.uniform(45, 240), 1),
        }
    else:
        body = _load("call_hotel.json")
    return body, _headers()


def _headers() -> dict:
    return {
        "x-ratelimit-remaining": str(random.randint(80, 120)),
        "x-monthly-quota-remaining": str(random.randint(900, 1000)),
        "x-ratelimit-reset": "60",
    }
