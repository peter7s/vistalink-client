# Tool Setup Guide

How to set up and invoke the four VistaLink tools (`search_hotels`, `chat_about_hotels`, `get_hotel_details`, `call_hotel`) using this reference client.

## Prerequisites

- Python 3.13+
- A VistaLink API key (`vl_test_*` for sandbox, `vl_live_*` for live billing)
- `git`

## 1. Install

```bash
git clone https://github.com/peter7s/vistalink-client.git
cd vistalink-client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
VL_API_KEY=vl_test_your_key_here     # or vl_live_*
VL_MODE=live                         # or `mock` for offline fixtures
VL_API_BASE=https://api.vistalink.com
```

## 3. Run the proxy

```bash
uvicorn proxy.main:app --reload --port 8787
```

Leave running. Web UI: `http://localhost:8787/`. Verify with `curl http://localhost:8787/stats`.

---

## search_hotels

**Endpoint:** `POST /v1/search`
**Cost:** $0.01/call

CLI:
```bash
python -m cli.vl search --city Paris --limit 5
```

All params: `--city`, `--country`, `--check-in`, `--check-out`, `--guests`, `--rooms`, `--budget-min`, `--budget-max`, `--currency`, `--amenities`, `--hotel-name`, `--limit`, `--include-rates`.

Frontend: **Search** tab.

REST:
```bash
curl -X POST http://localhost:8787/search \
  -H "Content-Type: application/json" \
  -d '{"city":"Paris","limit":5}'
```

## chat_about_hotels

**Endpoint:** `POST /v1/chat`
**Cost:** $0.03/call (~15–20s latency, LLM inference)

CLI:
```bash
python -m cli.vl chat "cozy boutique hotel in paris under 300"
```

Multi-turn: pass `--session <session_id>` from a prior response.

All params: `--session`, `--guest`, `--locale`, `--currency`, `--clarification-id`, `--clarification-option-id`.

Frontend: **Chat** tab. Session ID persists automatically across messages.

REST:
```bash
curl -X POST http://localhost:8787/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"cozy boutique hotel in paris under 300"}'
```

## get_hotel_details

**Endpoint:** `GET /v1/hotels/{hotel_id}`
**Cost:** $0.005/call

CLI:
```bash
python -m cli.vl details <hotel_id>
```

Optional: `--currency <ISO4217>`.

Frontend: **Details** tab, or click any card in Search / pill in Chat.

REST:
```bash
curl http://localhost:8787/details/<hotel_id>
```

## call_hotel

**Endpoint:** `POST /v1/call` (single dispatcher; `scenario` selects playbook)
**Cost:** $0.50 base + $0.05/min over 10 minutes
**Tier:** Pro/Enterprise only. Free-tier keys return HTTP 403.

Three scenarios: `hotel_negotiation` (default), `hotel_confirm_booking`, `hotel_cancel_booking`.

**Async lifecycle:** dispatch → poll status → fetch results.

CLI (dispatch + auto-poll + fetch results):
```bash
python -m cli.vl call <hotel_id> \
  --phone "+33146340212" \
  --name "Hotel Name" \
  --scenario hotel_negotiation \
  --price 280 --currency EUR \
  --check-in 2026-07-01 --check-out 2026-07-03 \
  --language fr \
  --instructions "Aim for 240 EUR/night. Emphasize direct booking." \
  --wait
```

CLI (separate status/results commands):
```bash
python -m cli.vl call-status <call_id>
python -m cli.vl call-results <call_id>
```

All params: `--phone`, `--name`, `--scenario`, `--language`, `--price`, `--currency`, `--check-in`, `--check-out`, `--conf` (confirmation number), `--instructions`, `--wait`.

Frontend: **Call** tab, or click `📞 Call this hotel` on the Details view (auto-fills hotel_id, phone, name).

REST:
```bash
# Dispatch
curl -X POST http://localhost:8787/call \
  -H "Content-Type: application/json" \
  -d '{"hotel_id":"...","phone_number":"+33...","hotel_name":"...","scenario":"hotel_negotiation"}'

# Poll
curl http://localhost:8787/call/<call_id>/status

# Fetch results once status=completed
curl http://localhost:8787/call/<call_id>/results
```

Required body fields: `hotel_id`, `phone_number` (E.164, from `get_hotel_details.phone_number`), `hotel_name`.

---

## Verification

```bash
python -m cli.vl stats     # per-tool rollup: count, fail%, schema%, p50/p95 latency, cost
pytest -v                  # 7 contract + parity tests
```

## Mock mode (no live API calls)

Set `VL_MODE=mock` in `.env` and restart the proxy. All four tools work against local fixtures in [fixtures/](fixtures/). `call_hotel` simulates the dispatching → in_progress → completed lifecycle over ~6 seconds. Useful for offline development, CI, and demos.

## Optional surfaces

- **MCP server** (for Claude Desktop / Claude Code): `python -m proxy.mcp_server` — exposes the four tools over MCP stdio. See [README.md](README.md) for the JSON config snippet.
- **LLM agent harness** (Claude or GPT driving the tools): `python -m cli.agent "find me a cozy boutique hotel in paris"`. Requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`.
