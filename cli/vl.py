import json
import os
import sys

import httpx
import typer
from rich import print
from rich.table import Table

app = typer.Typer(add_completion=False)
PROXY = os.getenv("VL_PROXY", "http://localhost:8787")


def _client() -> httpx.Client:
    return httpx.Client(base_url=PROXY, timeout=120)


@app.command()
def search(
    query: str = "",
    city: str = "",
    country: str = "",
    check_in: str = "",
    check_out: str = "",
    guests: int = 0,
    rooms: int = 0,
    budget_min: float = 0.0,
    budget_max: float = 0.0,
    currency: str = "",
    amenities: str = "",
    hotel_name: str = "",
    limit: int = 5,
    include_rates: bool = False,
):
    """Structured hotel search. `query` populates `vibe` if no other vibe-ish filter set."""
    payload: dict = {"limit": limit, "include_rates": include_rates}
    for k, v in {
        "city": city, "country": country, "check_in": check_in, "check_out": check_out,
        "currency": currency, "amenities": amenities, "hotel_name": hotel_name,
    }.items():
        if v:
            payload[k] = v
    for k, v in {"guests": guests, "rooms": rooms, "budget_min": budget_min, "budget_max": budget_max}.items():
        if v:
            payload[k] = v
    if query:
        payload["vibe"] = query
    with _client() as c:
        r = c.post("/search", json=payload)
    _render_results(r.json())


@app.command()
def chat(
    message: str,
    session: str = "",
    guest: str = "",
    locale: str = "",
    currency: str = "",
    clarification_id: str = "",
    clarification_option_id: str = "",
):
    """Conversational hotel search. Pass --session to continue a multi-turn convo."""
    payload: dict = {"message": message}
    for k, v in {
        "session_id": session, "guest_id": guest, "locale": locale, "currency": currency,
        "clarification_id": clarification_id, "clarification_option_id": clarification_option_id,
    }.items():
        if v:
            payload[k] = v
    with _client() as c:
        r = c.post("/chat", json=payload)
    body = r.json()
    print(f"[bold]{body.get('message','')}[/bold]")
    _render_results(body)
    if body.get("session_id"):
        print(f"\n[dim]session_id: {body['session_id']}[/dim]")
    clar = body.get("clarification_pending")
    if clar:
        print(f"\n[yellow]{clar.get('question', 'Clarification needed:')}[/yellow]")
        for opt in clar.get("options", []):
            desc = f" — {opt['description']}" if opt.get("description") else ""
            print(f"  [{opt.get('id')}] {opt.get('label')}{desc}")
        if clar.get("allow_free_text"):
            print("[dim](free-text reply allowed)[/dim]")


@app.command()
def details(hotel_id: str, currency: str = ""):
    params = {"currency": currency} if currency else {}
    with _client() as c:
        r = c.get(f"/details/{hotel_id}", params=params)
    print(json.dumps(r.json(), indent=2))


@app.command()
def call(
    hotel_id: str,
    phone_number: str = typer.Option(..., "--phone", help="E.164, e.g. +390551234567"),
    hotel_name: str = typer.Option(..., "--name", help="Hotel name (voice agent identifies itself)"),
    scenario: str = typer.Option("hotel_negotiation", "--scenario", help="hotel_negotiation | hotel_confirm_booking | hotel_cancel_booking"),
    language: str = typer.Option("", "--language"),
    booking_price: float = typer.Option(0.0, "--price"),
    currency: str = typer.Option("", "--currency"),
    check_in: str = typer.Option("", "--check-in"),
    check_out: str = typer.Option("", "--check-out"),
    confirmation_number: str = typer.Option("", "--conf"),
    caller_instructions: str = typer.Option("", "--instructions"),
    wait: bool = typer.Option(False, "--wait", help="Poll until completed and fetch results"),
):
    """Dispatch a voice call. Returns call_id immediately. Use --wait to poll-and-fetch."""
    payload: dict = {"hotel_id": hotel_id, "phone_number": phone_number, "hotel_name": hotel_name, "scenario": scenario}
    for k, v in {"language": language, "currency": currency, "check_in_date": check_in,
                 "check_out_date": check_out, "confirmation_number": confirmation_number,
                 "caller_instructions": caller_instructions}.items():
        if v:
            payload[k] = v
    if booking_price:
        payload["booking_price"] = booking_price

    with _client() as c:
        r = c.post("/call", json=payload)
        body = r.json()
    print(json.dumps(body, indent=2))
    call_id = body.get("call_id")
    if not wait or not call_id:
        return

    import time
    print(f"\n[dim]Polling status for {call_id}…[/dim]")
    while True:
        with _client() as c:
            s = c.get(f"/call/{call_id}/status").json()
        dur = s.get("duration_seconds")
        dur_str = f" ({dur}s)" if dur else ""
        print(f"[dim]  status: {s.get('status')}{dur_str}[/dim]")
        if s.get("status") in ("completed", "failed"):
            break
        time.sleep(2)

    print(f"\n[bold]Results:[/bold]")
    with _client() as c:
        results = c.get(f"/call/{call_id}/results").json()
    print(json.dumps(results, indent=2))


@app.command(name="call-status")
def call_status_cmd(call_id: str):
    """GET /call/{call_id}/status — poll the lifecycle of a dispatched call."""
    with _client() as c:
        r = c.get(f"/call/{call_id}/status")
    print(json.dumps(r.json(), indent=2))


@app.command(name="call-results")
def call_results_cmd(call_id: str):
    """GET /call/{call_id}/results — fetch transcript + outcome once status is completed."""
    with _client() as c:
        r = c.get(f"/call/{call_id}/results")
    print(json.dumps(r.json(), indent=2))


@app.command()
def stats():
    with _client() as c:
        r = c.get("/stats")
    s = r.json()
    print(f"[bold]Total calls:[/bold] {s.get('calls',0)}   [bold]Cost:[/bold] ${s.get('total_cost_usd',0)}")
    t = Table("tool", "count", "fail%", "schema%", "p50ms", "p95ms", "cost$")
    for tool, m in s.get("by_tool", {}).items():
        t.add_row(tool, str(m["count"]), f"{m['failure_rate']*100:.1f}", f"{m['schema_pass_rate']*100:.1f}",
                  str(m["p50_ms"]), str(m["p95_ms"]), str(m["cost_usd"]))
    print(t)


def _render_results(body: dict):
    """Render either /search response (hotels key) or /chat response (hotels key, often empty)."""
    hotels = body.get("hotels") or body.get("results") or []
    if not hotels:
        return
    t = Table("hotel_id", "name", "city", "★", "review", "type")
    for h in hotels:
        t.add_row(
            h.get("hotel_id", "")[:36],
            (h.get("name") or "")[:30],
            h.get("city") or "",
            str(h.get("star_rating") or ""),
            str(h.get("review_score") or ""),
            h.get("hotel_type") or "",
        )
    print(t)
    if body.get("total") is not None:
        print(f"\n[dim]total available: {body['total']}[/dim]")


if __name__ == "__main__":
    app()
