import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from proxy import schemas, metrics

FRONTEND_INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

# Auto-load .env from the project root so VL_API_KEY / VL_MODE / etc. just work.
load_dotenv()

MODE = os.getenv("VL_MODE", "mock")
if MODE == "live":
    from proxy import mcp_client as mcp
else:
    from proxy import mock_mcp as mcp

app = FastAPI(title="vistalink-harness proxy", version="0.1.0")


def _record_headers(row: dict, headers: dict):
    row["rate_limit_remaining"] = headers.get("x-ratelimit-remaining")
    row["monthly_quota_remaining"] = headers.get("x-monthly-quota-remaining")


def _record_validation(row: dict, body: dict, model: type[BaseModel]):
    valid, missing = metrics.validate(body, model)
    row["schema_valid"] = valid
    row["missing_fields"] = missing


@app.post("/search")
async def search(req: schemas.SearchRequest):
    payload = req.model_dump(exclude_none=True)
    with metrics.record("search_hotels", payload) as row:
        body, headers = await mcp.search_hotels(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.SearchResponse)
        # #5 image diagnostic: how many hotels came back with images, and how many each?
        hotels = body.get("hotels") or []
        img_counts = [len(h.get("images") or []) for h in hotels]
        row["image_stats"] = {
            "hotels_returned": len(hotels),
            "hotels_with_images": sum(1 for n in img_counts if n > 0),
            "avg_images_per_hotel": round(sum(img_counts) / len(img_counts), 2) if img_counts else 0,
            "max_images": max(img_counts) if img_counts else 0,
        }
        print(f"[images] {row['image_stats']}", flush=True)
        return body


@app.post("/chat")
async def chat(req: schemas.ChatRequest):
    payload = req.model_dump(exclude_none=True)
    with metrics.record("chat_about_hotels", payload) as row:
        body, headers = await mcp.chat_about_hotels(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.ChatResponse)
        return body


@app.get("/details/{hotel_id}")
async def details(hotel_id: str, currency: str | None = None):
    payload = {"currency": currency} if currency else {}
    with metrics.record("get_hotel_details", {"hotel_id": hotel_id, **payload}) as row:
        body, headers = await mcp.get_hotel_details(hotel_id, payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.HotelDetails)
        return body


@app.post("/call")
async def call(req: schemas.CallRequest):
    """Dispatch a voice call. Returns immediately with call_id; poll /call/{id}/status."""
    payload = req.model_dump(exclude_none=True)
    with metrics.record("call_hotel", payload) as row:
        body, headers = await mcp.call_hotel(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallDispatched)
        return body


@app.get("/call/{call_id}/status")
async def call_status(call_id: str):
    with metrics.record("call_hotel_status", {"call_id": call_id}) as row:
        body, headers = await mcp.get_call_status(call_id)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallStatus)
        return body


@app.get("/call/{call_id}/results")
async def call_results(call_id: str):
    with metrics.record("call_hotel_results", {"call_id": call_id}) as row:
        body, headers = await mcp.get_call_results(call_id)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        if body.get("duration_seconds") is not None:
            row["duration_seconds"] = body["duration_seconds"]
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallResults)
        return body


@app.get("/stats")
def stats():
    return metrics.rollup()


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_INDEX)
