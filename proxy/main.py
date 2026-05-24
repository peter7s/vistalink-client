import os
import re
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from proxy import schemas, metrics, monitor

# Matches `/room/<urlencoded_name>/` in VistaLink image URLs.
_ROOM_URL_PATTERN = re.compile(r"/room/([^/]+)/")


def _attach_room_images(body: dict) -> None:
    """VistaLink returns room photos in the top-level images[] (URL encodes the room
    name as a path segment). We bucket them onto each rooms[] entry by name match so
    clients can render per-room thumbnails without parsing URLs themselves."""
    rooms = body.get("rooms") or []
    images = body.get("images") or []
    if not rooms or not images:
        return
    room_by_name = {r.get("name"): r for r in rooms if r.get("name")}
    for img in images:
        url = img.get("url", "")
        m = _ROOM_URL_PATTERN.search(url)
        if not m:
            continue
        room_name = unquote(m.group(1))
        room = room_by_name.get(room_name)
        if room is not None:
            room.setdefault("images", []).append(img)

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


def _finalize_row(row: dict, body: dict, headers: dict, request: dict):
    """Common monitor bookkeeping called inside every route's record() context."""
    row["response_body"] = body
    row["result_summary"] = monitor.compute_result_summary(row["tool"], request, body, row.get("status_code"), headers)


@app.post("/search")
async def search(req: schemas.SearchRequest, x_customer_id: str = Header(default="default")):
    payload = req.model_dump(exclude_none=True)
    with metrics.record("search_hotels", payload, cid=x_customer_id) as row:
        body, headers = await mcp.search_hotels(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.SearchResponse)
        # Image diagnostic: how many hotels came back with images, and how many each?
        hotels = body.get("hotels") or []
        img_counts = [len(h.get("images") or []) for h in hotels]
        row["image_stats"] = {
            "hotels_returned": len(hotels),
            "hotels_with_images": sum(1 for n in img_counts if n > 0),
            "avg_images_per_hotel": round(sum(img_counts) / len(img_counts), 2) if img_counts else 0,
            "max_images": max(img_counts) if img_counts else 0,
        }
        print(f"[images] {row['image_stats']}", flush=True)
        _finalize_row(row, body, headers, payload)
        return body


@app.post("/chat")
async def chat(req: schemas.ChatRequest, x_customer_id: str = Header(default="default")):
    payload = req.model_dump(exclude_none=True)
    with metrics.record("chat_about_hotels", payload, cid=x_customer_id) as row:
        body, headers = await mcp.chat_about_hotels(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.ChatResponse)
        _finalize_row(row, body, headers, payload)
        return body


@app.get("/details/{hotel_id}")
async def details(hotel_id: str, currency: str | None = None, x_customer_id: str = Header(default="default")):
    payload = {"currency": currency} if currency else {}
    request_for_log = {"hotel_id": hotel_id, **payload}
    with metrics.record("get_hotel_details", request_for_log, cid=x_customer_id) as row:
        row["hid"] = hotel_id
        body, headers = await mcp.get_hotel_details(hotel_id, payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        if isinstance(body, dict) and "error" not in body:
            _attach_room_images(body)
        _record_validation(row, body, schemas.HotelDetails)
        _finalize_row(row, body, headers, request_for_log)
        return body


@app.post("/call")
async def call(req: schemas.CallRequest, x_customer_id: str = Header(default="default")):
    """Dispatch a voice call. Returns immediately with call_id; poll /call/{id}/status."""
    payload = req.model_dump(exclude_none=True)
    with metrics.record("call_hotel", payload, cid=x_customer_id) as row:
        row["hid"] = req.hotel_id
        body, headers = await mcp.call_hotel(payload)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallDispatched)
        _finalize_row(row, body, headers, payload)
        return body


@app.get("/call/{call_id}/status")
async def call_status(call_id: str, x_customer_id: str = Header(default="default")):
    request_for_log = {"call_id": call_id}
    with metrics.record("call_hotel_status", request_for_log, cid=x_customer_id) as row:
        body, headers = await mcp.get_call_status(call_id)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallStatus)
        _finalize_row(row, body, headers, request_for_log)
        return body


@app.get("/call/{call_id}/results")
async def call_results(call_id: str, x_customer_id: str = Header(default="default")):
    request_for_log = {"call_id": call_id}
    with metrics.record("call_hotel_results", request_for_log, cid=x_customer_id) as row:
        body, headers = await mcp.get_call_results(call_id)
        row["status_code"] = int(headers.get("x-upstream-status", 200))
        if body.get("duration_seconds") is not None:
            row["duration_seconds"] = body["duration_seconds"]
        _record_headers(row, headers)
        _record_validation(row, body, schemas.CallResults)
        _finalize_row(row, body, headers, request_for_log)
        return body


@app.get("/stats")
def stats():
    return metrics.rollup()


@app.get("/monitor")
def monitor_list(
    tool: str | None = None,
    cid: str | None = None,
    hid: str | None = None,
    errors_only: bool = False,
    text: str | None = None,
    limit: int = 200,
):
    """List recent calls with filters + stats + distinct CID/HID values for filter dropdowns."""
    return monitor.list_calls(tool=tool, cid=cid, hid=hid, errors_only=errors_only, text=text, limit=limit)


@app.get("/monitor/call/{proxy_call_id}")
def monitor_detail(proxy_call_id: str):
    row = monitor.get_call(proxy_call_id)
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return row


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_INDEX)
