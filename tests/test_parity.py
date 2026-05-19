"""Parity test: harness chat response vs. captured Parley result.

How to add a golden:
1. In Parley, run a hotel query.
2. Open browser DevTools → Network → click the API call → "Copy → Copy response".
3. Save to tests/goldens/parley_chat_<scenario>.json (any filename matching parley_chat_*.json).

Each test compares STRUCTURE (which keys/fields exist), not values — rates, IDs,
and prose vary per run. If Parley exposes a field our harness doesn't, the diff
makes it actionable: either we add the field to schemas.py, or Parley has data
VistaLink doesn't expose to us (worth flagging to VistaLink).
"""
import json
from pathlib import Path

import pytest

from proxy import schemas

GOLDENS = Path(__file__).resolve().parent / "goldens"
HARNESS_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "chat_about_hotels.json"


def _golden_files():
    if not GOLDENS.exists():
        return []
    return sorted(GOLDENS.glob("parley_chat_*.json"))


def _hotel_list(payload: dict) -> list[dict]:
    """Find the hotel array regardless of which key the system uses.
    Parley uses `hotels_core`; VistaLink /v1/chat uses `hotels`."""
    for key in ("hotels_core", "hotels", "results", "properties", "items", "data"):
        if isinstance(payload.get(key), list) and payload[key]:
            return payload[key]
    return []


@pytest.mark.parametrize("golden_path", _golden_files())
def test_top_level_field_parity(golden_path):
    """Every top-level field Parley returns should exist on our schemas.ChatResponse model
    (or be allowlisted as Parley-only orchestration data we don't expect VistaLink to emit)."""
    golden = json.loads(golden_path.read_text())
    g_keys = set(golden.keys())
    model_keys = set(schemas.ChatResponse.model_fields.keys())

    # Parley-only fields VistaLink's public chat probably won't emit — informational, not errors:
    parley_only = {
        "trace_id", "model", "thread_id", "prompt",
        "intent", "route", "thinking_steps", "phase",
        "reply", "count",  # parley uses 'reply'; vistalink uses 'message'
        "_capture",        # local-only metadata block we added to the golden
    }
    informational = (g_keys - model_keys) & parley_only
    actionable = (g_keys - model_keys) - parley_only

    if informational:
        print(f"\n[INFO] Parley-only top-level fields (VistaLink may add later): {sorted(informational)}")

    assert not actionable, (
        f"Parley response has top-level fields our schemas.ChatResponse is missing: {sorted(actionable)}\n"
        f"Add each to ChatResponse (or to parley_only allowlist if VistaLink won't emit them)."
    )


@pytest.mark.parametrize("golden_path", _golden_files())
def test_hotel_card_field_parity(golden_path):
    """Every hotel-card field Parley exposes should exist on our schemas.Hotel model.
    We compare against the pydantic model's declared fields (not the harness fixture)
    so the test is meaningful even when the live /v1/chat returns empty hotels."""
    golden = json.loads(golden_path.read_text())
    g_hotels = _hotel_list(golden)
    if not g_hotels:
        pytest.skip(f"Golden {golden_path.name} has no hotels list — top-level parity test still ran")

    g_keys = set(g_hotels[0].keys())
    model_keys = set(schemas.Hotel.model_fields.keys())
    # Map Parley field names to harness equivalents (semantic aliases — same data, different names):
    aliases = {
        "id": "hotel_id",      # Parley uses `id`; our model uses `hotel_id`
        "stars": "star_rating",
    }
    # Treat aliased Parley fields as present if the harness equivalent is declared.
    g_keys_normalized = {aliases.get(k, k) for k in g_keys}
    missing = g_keys_normalized - model_keys

    # Parley-specific fields that VistaLink's public chat probably won't emit — informational, not errors:
    parley_only_card_fields = {
        # routing / scoring / explanation
        "score", "explanation", "explanation_factors",
        # POI distances + walking/driving geometry
        "poi_distances", "combined_poi_score", "avg_poi_distance",
        "nearest_poi", "distance_to_poi_meters", "poi_name", "poi_type",
        "routes_to_pois", "walk_duration_seconds", "walk_geometry",
        "drive_duration_seconds", "drive_geometry",
        # convenience flat-vs-nested duplicates
        "latitude", "longitude", "location",  # we have these as flat
        # other parley extras
        "amenity_ids", "hero_image_url", "hero_image_label", "booking_url", "rating",
    }
    informational = missing & parley_only_card_fields
    actionable = missing - parley_only_card_fields

    if informational:
        print(f"\n[INFO] Parley-only hotel-card fields (VistaLink may add these later): {sorted(informational)}")

    assert not actionable, (
        f"Parley hotel card has fields our schemas.Hotel model is missing: {sorted(actionable)}\n"
        f"Add each to schemas.Hotel (or to the parley_only_card_fields allowlist if VistaLink won't emit them)."
    )


def test_placeholder_when_no_goldens():
    if not _golden_files():
        pytest.skip(
            "No Parley goldens captured yet.\n"
            "Capture from Parley DevTools → save as tests/goldens/parley_chat_<scenario>.json.\n"
            "See module docstring for instructions."
        )
