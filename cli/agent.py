"""Agent harness: drives the proxy tools via an LLM (Claude or GPT).
Simulates what an AI-powered web/mobile app does under the hood — the LLM decides
which tool to call, the harness dispatches it to the FastAPI proxy.

Usage:
    python -m cli.agent "find me a boutique hotel in paris under 300"
    python -m cli.agent "ask the first one about late checkout" --model gpt

Requires ANTHROPIC_API_KEY (for claude) or OPENAI_API_KEY (for gpt).
The FastAPI proxy must be running (uvicorn proxy.main:app --port 8787).
"""
import json
import os

import httpx
import typer
from rich import print
from rich.panel import Panel

app = typer.Typer(add_completion=False)
PROXY = os.getenv("VL_PROXY", "http://localhost:8787")

TOOLS = [
    {
        "name": "search_hotels",
        "description": "Structured hotel search. Use when the user gives concrete filters (city, dates, budget, amenities).",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "country": {"type": "string", "description": "ISO 3166-1 alpha-2"},
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "radius_meters": {"type": "integer"},
                "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "YYYY-MM-DD"},
                "guests": {"type": "integer"},
                "rooms": {"type": "integer"},
                "budget_min": {"type": "number"},
                "budget_max": {"type": "number"},
                "currency": {"type": "string"},
                "amenities": {"type": "string", "description": "Comma-separated, e.g. 'wifi,pool,spa'"},
                "vibe": {"type": "string", "description": "Comma-separated tags, e.g. 'romantic,quiet'"},
                "hotel_name": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
                "include_rates": {"type": "boolean", "description": "Live rates; adds 30-45s latency"},
            },
        },
    },
    {
        "name": "chat_about_hotels",
        "description": "Conversational hotel search. Use for natural-language queries or multi-turn refinement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "session_id": {"type": "string", "description": "Pass to continue a prior conversation"},
                "guest_id": {"type": "string"},
                "currency": {"type": "string"},
                "locale": {"type": "string", "description": "e.g. 'en-GB', 'it-IT'"},
                "clarification_id": {"type": "string"},
                "clarification_option_id": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "get_hotel_details",
        "description": "Full record for a hotel by id (description, images, rooms, reviews, phone).",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_id": {"type": "string"},
                "currency": {"type": "string"},
            },
            "required": ["hotel_id"],
        },
    },
    {
        "name": "call_hotel",
        "description": "Dispatch an AI voice call to a hotel (negotiate, confirm, or cancel). Async — returns a call_id; poll status separately. Pro/Enterprise tier only against live API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_id": {"type": "string"},
                "phone_number": {"type": "string", "description": "E.164 format, e.g. +390551234567. Fetch from get_hotel_details first."},
                "hotel_name": {"type": "string", "description": "Used by the voice agent to introduce itself"},
                "scenario": {"type": "string", "enum": ["hotel_negotiation", "hotel_confirm_booking", "hotel_cancel_booking"]},
                "guest_first_name": {"type": "string"},
                "guest_last_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "check_in_date": {"type": "string", "description": "YYYY-MM-DD"},
                "check_out_date": {"type": "string", "description": "YYYY-MM-DD"},
                "number_of_rooms": {"type": "integer"},
                "number_of_people": {"type": "integer"},
                "booking_price": {"type": "number"},
                "room_type": {"type": "string"},
                "currency": {"type": "string"},
                "language": {"type": "string", "description": "e.g. 'en', 'it', 'fr' — voice agent switches TTS/STT accordingly"},
                "confirmation_number": {"type": "string", "description": "For confirm/cancel scenarios"},
                "special_requests": {"type": "string"},
                "caller_instructions": {"type": "string", "description": "Free-form coaching for the voice agent"},
            },
            "required": ["hotel_id", "phone_number", "hotel_name"],
        },
    },
    {
        "name": "get_call_status",
        "description": "Poll the status of a dispatched voice call. Returns dispatching | in_progress | completed | failed.",
        "input_schema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
    {
        "name": "get_call_results",
        "description": "Fetch the final transcript, summary, and structured outcome of a completed call. Returns 409 if not yet completed.",
        "input_schema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
]


def dispatch(name: str, args: dict) -> dict:
    """Route a tool call to the FastAPI proxy."""
    args = dict(args)
    with httpx.Client(base_url=PROXY, timeout=120) as c:
        if name == "search_hotels":
            return c.post("/search", json=args).json()
        if name == "chat_about_hotels":
            return c.post("/chat", json=args).json()
        if name == "get_hotel_details":
            hotel_id = args.pop("hotel_id")
            return c.get(f"/details/{hotel_id}", params=args).json()
        if name == "call_hotel":
            return c.post("/call", json=args).json()
        if name == "get_call_status":
            return c.get(f"/call/{args['call_id']}/status").json()
        if name == "get_call_results":
            return c.get(f"/call/{args['call_id']}/results").json()
    return {"error": f"unknown tool {name}"}


def run_anthropic(user_message: str):
    from anthropic import Anthropic
    client = Anthropic()
    messages = [{"role": "user", "content": user_message}]
    while True:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )
        tool_uses = []
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(Panel(block.text, title="Claude"))
            elif block.type == "tool_use":
                tool_uses.append(block)
                print(f"[cyan]→ {block.name}({json.dumps(block.input)})[/cyan]")
        if resp.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for tu in tool_uses:
            result = dispatch(tu.name, dict(tu.input))
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result)})
        messages.append({"role": "user", "content": results})


def run_openai(user_message: str):
    from openai import OpenAI
    client = OpenAI()
    tools_oa = [
        {"type": "function", "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        }} for t in TOOLS
    ]
    messages = [{"role": "user", "content": user_message}]
    while True:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools_oa)
        msg = resp.choices[0].message
        if msg.content:
            print(Panel(msg.content, title="GPT"))
        if not msg.tool_calls:
            break
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            print(f"[cyan]→ {tc.function.name}({json.dumps(args)})[/cyan]")
            result = dispatch(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})


@app.command()
def main(prompt: str, model: str = "claude"):
    """Drive the proxy via an LLM. model: claude (default) or gpt."""
    if model.lower() == "gpt":
        run_openai(prompt)
    else:
        run_anthropic(prompt)


if __name__ == "__main__":
    app()
