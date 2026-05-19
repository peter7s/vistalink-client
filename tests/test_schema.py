"""Contract tests: every mock response must satisfy the frontend schema.
If these pass, a client app's frontend can render every field it needs."""
import json
from pathlib import Path

import pytest

from proxy import schemas

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.parametrize(
    "filename,model",
    [
        ("search_hotels.json", schemas.SearchResponse),
        ("chat_about_hotels.json", schemas.ChatResponse),
        ("get_hotel_details.json", schemas.HotelDetails),
        ("call_hotel.json", schemas.CallResponse),
    ],
)
def test_fixture_matches_schema(filename, model):
    payload = json.loads((FIXTURES / filename).read_text())
    model.model_validate(payload)
