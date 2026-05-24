"""Monitor: read calls.jsonl into the dashboard surface (list, filter, stats, single-call detail)."""
import json
from pathlib import Path
from typing import Optional

from proxy.metrics import LOG_PATH


def _short(s: Optional[str], n: int = 8) -> str:
    return (s or "")[:n]


def compute_result_summary(tool: str, request: dict, response_body: dict, status_code: Optional[int], headers: dict | None = None) -> str:
    """Short human-readable one-liner shown in the monitor's RESULT column."""
    headers = headers or {}
    if status_code is None:
        return "no response (proxy exception)"
    if status_code == 429:
        retry = headers.get("retry-after") or headers.get("x-ratelimit-reset") or "?"
        return f"rate limit — Retry-After {retry}s"
    if status_code == 408 or status_code == 504:
        return "gateway timeout"
    if status_code >= 500:
        if tool == "get_hotel_details":
            hid = request.get("hotel_id", "")
            return f"hotel_id={_short(hid)} — upstream {status_code}"
        return f"upstream {status_code}"
    if status_code >= 400:
        err = (response_body or {}).get("error") if isinstance(response_body, dict) else None
        if isinstance(err, dict):
            return f"{status_code} {err.get('code') or err.get('message') or 'error'}"
        return f"upstream {status_code}"

    body = response_body if isinstance(response_body, dict) else {}
    if tool == "search_hotels":
        city = request.get("city")
        hotels = body.get("hotels") or []
        if city:
            return f"city={city}, {len(hotels)} results"
        if request.get("vibe"):
            return f"vibe search, {len(hotels)} hotels"
        return f"{len(hotels)} results"
    if tool == "chat_about_hotels":
        hotels = body.get("hotels") or []
        if request.get("session_id"):
            return f"session continued, {len(hotels)} hotels"
        return f"new session, {len(hotels)} hotels"
    if tool == "get_hotel_details":
        hid = request.get("hotel_id", "")
        return f"hotel_id={_short(hid)}, full profile"
    if tool == "call_hotel":
        call_id = body.get("call_id", "")
        scenario = request.get("scenario", "negotiation")
        return f"call_id={_short(call_id, 10)}, {scenario.replace('hotel_', '').replace('_', ' ')}"
    if tool == "call_hotel_status":
        call_id = request.get("call_id", "")
        return f"call_id={_short(call_id, 10)}, status={body.get('status', '?')}"
    if tool == "call_hotel_results":
        call_id = request.get("call_id", "")
        outputs = body.get("structured_outputs") or {}
        outcome = outputs.get("outcome") or ("success" if body.get("status") == "completed" else body.get("status"))
        return f"call_id={_short(call_id, 10)}, {outcome}"
    return f"{tool} ok"


def _read_all() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]


def _row_summary(row: dict) -> dict:
    """Trimmed row sent to the table view — full body lives on the detail endpoint."""
    return {
        "proxy_call_id": row.get("proxy_call_id"),
        "ts": row.get("ts"),
        "tool": row.get("tool"),
        "cid": row.get("cid"),
        "hid": row.get("hid"),
        "status_code": row.get("status_code"),
        "latency_ms": row.get("latency_ms"),
        "estimated_cost_usd": row.get("estimated_cost_usd"),
        "result_summary": row.get("result_summary"),
        "schema_valid": row.get("schema_valid"),
    }


def list_calls(
    tool: Optional[str] = None,
    cid: Optional[str] = None,
    hid: Optional[str] = None,
    errors_only: bool = False,
    text: Optional[str] = None,
    limit: int = 200,
) -> dict:
    rows = _read_all()
    if tool:
        rows = [r for r in rows if r.get("tool") == tool or r.get("tool", "").startswith(tool)]
    if cid:
        rows = [r for r in rows if r.get("cid") == cid]
    if hid:
        rows = [r for r in rows if r.get("hid") == hid]
    if errors_only:
        rows = [r for r in rows if (r.get("status_code") or 0) >= 400 or r.get("schema_valid") is False]
    if text:
        t = text.lower()
        rows = [r for r in rows if t in json.dumps(r, default=str).lower()]

    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    paged = rows[:limit]

    # Stats over the *filtered* set so users get feedback as they slice
    total = len(rows)
    if total:
        successes = sum(1 for r in rows if 200 <= (r.get("status_code") or 0) < 400)
        attention = sum(1 for r in rows if (r.get("status_code") or 0) >= 400 or r.get("schema_valid") is False)
        lats = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
        avg_latency = round(sum(lats) / len(lats), 1) if lats else 0
        success_rate = round(successes / total * 100, 1)
    else:
        attention = 0
        avg_latency = 0
        success_rate = 0.0

    # Distinct values for filter dropdowns (always over the unfiltered set)
    all_rows = _read_all()
    cids = sorted({r.get("cid") for r in all_rows if r.get("cid")})
    hids = sorted({r.get("hid") for r in all_rows if r.get("hid")})

    return {
        "stats": {
            "total_calls": total,
            "success_rate": success_rate,
            "needs_attention": attention,
            "avg_latency_ms": avg_latency,
        },
        "calls": [_row_summary(r) for r in paged],
        "cids": cids,
        "hids": hids,
        "total_unfiltered": len(all_rows),
    }


def get_call(proxy_call_id: str) -> Optional[dict]:
    for r in _read_all():
        if r.get("proxy_call_id") == proxy_call_id:
            return r
    return None
