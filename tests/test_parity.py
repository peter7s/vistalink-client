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

GOLDENS = Path(__file__).resolve().parent / "goldens"
HARNESS_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "chat_about_hotels.json"


def _golden_files():
    if not GOLDENS.exists():
        return []
    return sorted(GOLDENS.glob("parley_chat_*.json"))


def _hotel_list(payload: dict) -> list[dict]:
    """Find the hotel array regardless of which key the system uses."""
    for key in ("hotels", "results", "properties", "items", "data"):
        if isinstance(payload.get(key), list) and payload[key]:
            return payload[key]
    return []


@pytest.mark.parametrize("golden_path", _golden_files())
def test_top_level_field_parity(golden_path):
    """Every top-level field Parley returns should exist (or be defensible to omit) in our harness."""
    golden = json.loads(golden_path.read_text())
    harness = json.loads(HARNESS_FIXTURE.read_text())

    g_keys = set(golden.keys())
    h_keys = set(harness.keys())
    missing = g_keys - h_keys
    # Allow Parley-specific orchestration fields we wouldn't expect VistaLink to emit:
    parley_only = {"trace_id", "model", "thread_id", "prompt", "intent"}
    missing -= parley_only

    assert not missing, (
        f"Parley response (top-level) has fields the harness response is missing: {sorted(missing)}\n"
        f"Decide per field: (a) add to ChatResponse, (b) ignore if Parley-only orchestration."
    )


@pytest.mark.parametrize("golden_path", _golden_files())
def test_hotel_card_field_parity(golden_path):
    """Every hotel-card field Parley exposes per result should exist on our Hotel model.
    Skips cleanly if either side has no hotels in this scenario."""
    golden = json.loads(golden_path.read_text())
    harness = json.loads(HARNESS_FIXTURE.read_text())

    g_hotels = _hotel_list(golden)
    h_hotels = _hotel_list(harness)
    if not g_hotels:
        pytest.skip(f"Golden {golden_path.name} has no hotels list — top-level parity test still ran")
    if not h_hotels:
        pytest.skip("Harness fixture has no hotels list (expected — chat returns empty hotels until VistaLink fixes the regression)")

    g_keys = set(g_hotels[0].keys())
    h_keys = set(h_hotels[0].keys())
    missing = g_keys - h_keys
    assert not missing, (
        f"Parley hotel card has fields the harness Hotel model doesn't expose: {sorted(missing)}\n"
        f"For each field, either add it to schemas.Hotel or document why VistaLink can't provide it."
    )


def test_placeholder_when_no_goldens():
    if not _golden_files():
        pytest.skip(
            "No Parley goldens captured yet.\n"
            "Capture from Parley DevTools → save as tests/goldens/parley_chat_<scenario>.json.\n"
            "See module docstring for instructions."
        )
