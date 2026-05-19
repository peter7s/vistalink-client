# vistalink-client

**Reference client app for the [VistaLink API](https://vistalink.com/developers).** Runs against the live API; ships with a mock backend for offline development and contributor onboarding (no API key needed to get started).

Covers both transports a real client might use — REST (for web/mobile app backends) and MCP (for Claude Desktop / Claude Code / any MCP-native agent) — against the same underlying code.

## What it does
- **REST proxy** (FastAPI) — owns the API key, mirrors the four VistaLink tools, logs every call. The shape a web or mobile app's own backend would take.
- **MCP server** — exposes the same tools over the MCP JSON-RPC stdio protocol. The shape Claude Desktop / Claude Code or any MCP-native client connects to.
- **CLI** (`vl`) — drives the REST proxy from the terminal.
- **Agent harness** (`agent`) — drives the REST proxy via Claude or GPT, demonstrating an LLM-powered client.
- **Mock backend** — fixture- and faker-backed stub. Lets you develop, demo, and run CI without burning real API calls or needing a key.
- **Contract tests** — every response is validated against `schemas.py`, the canonical "what a frontend needs to render a hotel card."

## Architecture

```
                  ┌──────────────────────────────────────┐
   Web/Mobile ───►│  FastAPI proxy  (proxy/main.py)      │
   CLI        ───►│  REST  ·  port 8787                  │──┐
   Agent      ───►│                                       │  │
                  └──────────────────────────────────────┘  │
                                                            ▼
                  ┌──────────────────────────────────────┐  ┌──────────────────┐
   Claude     ───►│  MCP server  (proxy/mcp_server.py)   │─►│  Backend         │
   Desktop        │  JSON-RPC over stdio                  │  │  mock OR live    │
                  └──────────────────────────────────────┘  └──────────────────┘
```

Both transports share the same backend (`mock_mcp.py` or `mcp_client.py`) and the same metrics pipeline.

## Setup
```bash
cd ~/Desktop/VL/vistalink-test-harness
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Switch to the real API anywhere: `VL_MODE=live VL_API_KEY=vl_test_...`. Default is `VL_MODE=mock`.

## VistaLink endpoint coverage (current state)
| Tool | Real endpoint | Live mode | Mock mode |
|---|---|---|---|
| Search | `POST /v1/search` | ✅ verified 2026-05-18 | ✅ |
| Chat | `POST /v1/chat` | ✅ verified 2026-05-18 | ✅ |
| Hotel details | `GET /v1/hotels/{id}` | ⚠️ upstream returns HTTP 500 (see below) | ✅ |
| Voice / call | `POST /v1/hotel/{negotiate,confirm-booking,cancel-booking,callback}` + async polling | ⛔ pending refactor | ✅ (legacy single-call mock) |

**Known upstream issue (2026-05-18):** `GET /v1/hotels/{id}` returns `HTTP 500 Internal Server Error` from VistaLink's server (`server: cloudflare → railway/europe-west4`) for hotel IDs returned by `/v1/search`. The harness's defensive error handling captures the upstream status in [proxy/mcp_client.py](proxy/mcp_client.py) and surfaces it as a structured error response. To be reported to VistaLink.

Voice/call works against the mock for demos, but live voice testing is deferred — the harness still targets the deprecated `POST /v1/call`. To be addressed in a follow-up.

## Live-mode smoke test (do this first with your real key)
```bash
export VL_API_KEY=vl_test_...   # or vl_live_...
VL_MODE=live uvicorn proxy.main:app --reload --port 8787

# In another terminal — start gentle:
python -m cli.vl search --city Paris --limit 3
python -m cli.vl chat "cozy boutique hotel in paris under 300/night"
python -m cli.vl details <hotel_id_from_search>

# Then check what landed in the logs:
python -m cli.vl stats
```

**What to look for:**
- HTTP `200` (not 401/404/422)
- `schema_pass_rate` in stats — if < 1.0, the real API returns fields our [proxy/schemas.py](proxy/schemas.py) doesn't model. Inspect `missing_fields` in `logs/calls.jsonl` and we update the schemas.
- `rate_limit_remaining` headers populating.

The proxy now validates inbound payloads too (typos like `budgt_max` get a 422 before they ever hit VistaLink — saves billable calls).

---

## Approach 1 — Test as a web/mobile app (REST proxy)

```bash
VL_MODE=mock uvicorn proxy.main:app --reload --port 8787
```

Drive it from the CLI in another terminal:
```bash
python -m cli.vl search "boutique hotel paris under 300"
python -m cli.vl details hotel_abc123
python -m cli.vl chat "find me something walkable near the Louvre"
python -m cli.vl call hotel_abc123 --message "ask about late checkout"
```

Inspect the auto-generated OpenAPI spec at http://localhost:8787/docs — this is what a frontend or LLM toolchain consumes.

## Approach 2 — Test as an AI-agent web/mobile app (LLM-driven REST)

The agent harness uses Claude or GPT to decide which tool to call, then hits the same FastAPI proxy. This is what an AI-powered partner app looks like in production.

```bash
# Proxy must be running (Approach 1)
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY for --model gpt

python -m cli.agent "find me a cozy boutique hotel in paris under 300/night"
python -m cli.agent "now call the first one and ask about late checkout"
python -m cli.agent "compare prices for the marais hotels" --model gpt
```

You'll see each tool call printed as Claude/GPT decides to fire it, then the model's final response.

## Approach 3 — Test as an MCP-native client (Claude Desktop)

```bash
VL_MODE=mock python -m proxy.mcp_server
```

This runs an MCP server over stdio. Register it in **Claude Desktop** by adding to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vistalink": {
      "command": "/full/path/to/vistalink-test-harness/.venv/bin/python",
      "args": ["-m", "proxy.mcp_server"],
      "cwd": "/full/path/to/vistalink-test-harness",
      "env": { "VL_MODE": "mock" }
    }
  }
}
```

Restart Claude Desktop. It will list the four VistaLink tools, and you can chat normally — "find me a boutique hotel in paris" — and Claude will call the tools natively.

For **Claude Code**, the same JSON shape goes in your `.mcp.json` or via `claude mcp add`.

---

## Switching transports for a given test
| You want to simulate | Run | Drive with |
|---|---|---|
| Web/mobile app backend | `uvicorn proxy.main:app --port 8787` | `python -m cli.vl ...` or curl |
| AI-agent in a web app | `uvicorn proxy.main:app --port 8787` | `python -m cli.agent "..."` |
| Claude Desktop / MCP client | `python -m proxy.mcp_server` | Claude Desktop UI |

All three log to the same `logs/calls.jsonl`, so `python -m cli.vl stats` rolls up calls regardless of which transport made them.

---

## Metrics
Every call appends one JSON row to `logs/calls.jsonl`:
- latency, status, error code, rate-limit headers, schema-pass, missing fields, estimated cost, retry count.

`python -m cli.vl stats` → per-tool rollup (failure rate, p50/p95 latency, schema-pass rate, cost).

## Parity testing
Drop captured Parley result JSON into `tests/goldens/` and `test_parity.py` will diff the harness's `chat_about_hotels` response against it. Run `pytest -v`.
