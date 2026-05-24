import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "calls.jsonl"
RESPONSE_BODY_LIMIT = 50_000  # truncate stored response bodies past this many chars

COST_PER_CALL = {
    "search_hotels": 0.01,
    "chat_about_hotels": 0.03,
    "get_hotel_details": 0.005,
    "call_hotel": 0.50,
}


def estimate_cost(tool: str, duration_seconds: float = 0.0) -> float:
    base = COST_PER_CALL.get(tool, 0.0)
    if tool == "call_hotel":
        return round(base + 0.05 * (duration_seconds / 60.0), 4)
    return base


def validate(payload: dict, model: type[BaseModel]) -> tuple[bool, list[str]]:
    try:
        model.model_validate(payload)
        return True, []
    except ValidationError as e:
        missing = [".".join(str(p) for p in err["loc"]) for err in e.errors()]
        return False, missing


def _truncate_for_log(body: Any) -> Any:
    """Cap response bodies stored in the log so a runaway transcript doesn't bloat the file."""
    try:
        s = json.dumps(body, default=str)
    except (TypeError, ValueError):
        return {"_error": "non-serializable response body"}
    if len(s) <= RESPONSE_BODY_LIMIT:
        return body
    return {"_truncated": True, "_original_size": len(s), "_preview": s[:RESPONSE_BODY_LIMIT]}


@contextmanager
def record(tool: str, request: dict, cid: str = "default"):
    """Wrap an MCP call. Yields a dict; mutate it then exit the context to log.
    Set row['response_body'] and row['hid'] inside the with-block for full monitor support."""
    row: dict[str, Any] = {
        "proxy_call_id": uuid.uuid4().hex,
        "tool": tool,
        "cid": cid,
        "hid": None,                  # mutate to the relevant hotel_id when applicable
        "request": request,
        "response_body": None,        # mutate to the upstream response
        "result_summary": None,       # mutate to a short human-readable line
        "ts": time.time(),
        "status_code": None,
        "error_code": None,
        "rate_limit_remaining": None,
        "monthly_quota_remaining": None,
        "schema_valid": None,
        "missing_fields": [],
        "retry_count": 0,
        "estimated_cost_usd": 0.0,
    }
    t0 = time.perf_counter()
    try:
        yield row
    finally:
        row["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        if tool == "call_hotel":
            row["estimated_cost_usd"] = estimate_cost(tool, row.get("duration_seconds") or 0.0)
        else:
            row["estimated_cost_usd"] = estimate_cost(tool)
        if row.get("response_body") is not None:
            row["response_body"] = _truncate_for_log(row["response_body"])
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")


def rollup() -> dict:
    if not LOG_PATH.exists():
        return {"calls": 0}
    rows = [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]
    if not rows:
        return {"calls": 0}
    by_tool: dict[str, list[dict]] = {}
    for r in rows:
        by_tool.setdefault(r["tool"], []).append(r)

    def pct(xs: list[float], p: float) -> float:
        if not xs:
            return 0.0
        s = sorted(xs)
        k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
        return round(s[k], 2)

    out = {"calls": len(rows), "total_cost_usd": round(sum(r["estimated_cost_usd"] for r in rows), 4), "by_tool": {}}
    for tool, items in by_tool.items():
        lats = [r["latency_ms"] for r in items if r.get("latency_ms") is not None]
        failures = sum(1 for r in items if (r.get("status_code") or 0) >= 400)
        schema_pass = sum(1 for r in items if r.get("schema_valid"))
        out["by_tool"][tool] = {
            "count": len(items),
            "failure_rate": round(failures / len(items), 3),
            "schema_pass_rate": round(schema_pass / len(items), 3),
            "p50_ms": pct(lats, 0.5),
            "p95_ms": pct(lats, 0.95),
            "cost_usd": round(sum(r["estimated_cost_usd"] for r in items), 4),
        }
    return out
