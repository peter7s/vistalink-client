"""Parity test: harness chat response vs. captured Parley result.
Drop a Parley-captured payload at tests/goldens/parley_chat_<n>.json with the same query."""
import json
from pathlib import Path

import pytest
from deepdiff import DeepDiff

GOLDENS = Path(__file__).resolve().parent / "goldens"


def _golden_files():
    if not GOLDENS.exists():
        return []
    return sorted(GOLDENS.glob("parley_chat_*.json"))


@pytest.mark.parametrize("golden_path", _golden_files())
def test_chat_field_parity(golden_path):
    """Check the harness response has every top-level result field Parley shows.
    We compare keys/structure, not values (rates and IDs differ between runs)."""
    golden = json.loads(golden_path.read_text())
    harness = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "chat_about_hotels.json").read_text())

    g_keys = set(golden["results"][0].keys()) if golden.get("results") else set()
    h_keys = set(harness["results"][0].keys()) if harness.get("results") else set()
    missing = g_keys - h_keys
    assert not missing, f"Harness card missing fields Parley exposes: {missing}"


def test_placeholder_when_no_goldens():
    if not _golden_files():
        pytest.skip("No Parley goldens captured yet. Add tests/goldens/parley_chat_*.json.")
