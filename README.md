# Merchant Agent Commerce System (MACS)

UAVS Hackathon 2026 · Team ClaudeMax Forever · FPT Australasia brief

A retailer-side layer that sells to autonomous AI shopping agents. It verifies the agent and its
mandate, decodes the buyer's intent into a structured object, matches the catalogue semantically,
composes a justified bundle, negotiates within merchant limits, and places the order through the
retailer's systems over MCP tools. The AI reasons; deterministic gates decide.

Hosted demo: https://merchant-agent-commerce-system.web.app

## One-command local setup

Requirements: Docker, an Anthropic API key, and Google Application Default Credentials for the
`merchant-agent-commerce-system` project (`gcloud auth application-default login`).

```
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

Console: http://localhost:8080 · API: http://localhost:8000/health · If 8080 is taken, set `WEB_PORT=8081`.

Offline development mode (no API key, no Firestore): from `backend/`, run
`FAKE_LLM=1 python -m uvicorn macs.app:app --port 8000` with `GOOGLE_CLOUD_PROJECT` unset. The
graph then runs with recorded model outputs against a seeded in-memory store. Start the console
with `npm run dev` in `frontend/` and open http://localhost:5173.

## Architecture

```
Buyer agent (external, simulated) --ACP-shaped message--> Protocol adapter
  -> Inbound gate      credentials, mandate, schema, injection screen        (deterministic)
  -> Intent decoder    Claude structured output -> Intent                     (LLM)
  -> Proposal engine   semantic_search + search_products over MCP,
                       Claude structured output -> Proposal with rationale    (LLM + tools)
  -> Outbound gate     grounding, discount cap, margin floor, claims, shipping (deterministic)
  -> Negotiate         buyer agent counters once, merchant re-proposes        (LLM, 2 rounds max)
  -> Execution gate    mandate cap, scope, expiry, signature presence         (deterministic)
  -> Retailer systems  create_order over MCP                                  (Firestore)
```

Three gates on three boundaries: validate what comes in, govern what goes out, authorise what
gets executed. Hard rules (`max_discount_pct`, `min_margin_pct`) live only in the gates and never
enter a model prompt, so a probing buyer agent cannot extract them and the retailer changes them
without re-prompting.

Every event of a run (messages, tool calls, gate verdicts, intent, proposals, order) is streamed
over SSE to the console and persisted to Firestore, which is what replay reads.

Stack: FastAPI, LangGraph, FastMCP, Anthropic API (Claude Haiku 4.5 by default, `MACS_MODEL` selects another model; structured outputs),
Firestore with native vector search, Vertex AI `text-embedding-005`, Vue 3 + Vite,
Cloud Run + Firebase Hosting.

## Repository

- `backend/macs/graph/` LangGraph state, nodes, gates, edges
- `backend/macs/mcp_server.py` FastMCP tools: search_products, semantic_search, get_product, get_price, get_shipping, create_order
- `backend/macs/store.py` Store interface: Firestore (production) and in-memory (tests)
- `backend/macs/app.py` FastAPI endpoints and SSE
- `backend/seed.py`, `backend/record.py` Firestore seeding, golden run recording
- `data/` mock catalogue (32 podcasting SKUs), merchant rules, mandates, credentials, injection patterns, replay recordings
- `frontend/` Vue console: pipeline strip, merchant console, agent-to-agent transcript
- `docs/superpowers/` design spec and implementation plan

## Tests

```
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

47 tests cover the contracts, store, seed data, emitter, LLM wrapper, MCP tools, all three gates,
every graph node, both scenarios end to end through LangGraph, and the HTTP API including SSE and
replay. Tests use recorded model outputs and an in-memory store; no network.

## Seeding and deploy

```
cd backend
.venv/Scripts/python seed.py --project merchant-agent-commerce-system          # governance + embedded catalogue + golden runs
.venv/Scripts/python record.py --project merchant-agent-commerce-system --scenario happy_path   # re-record a golden run live
cd .. && ANTHROPIC_API_KEY=sk-ant-... bash deploy.sh                           # Cloud Run + Firebase Hosting
```

The vector index on `catalogue.embedding` (768 dimensions, cosine) was created with
`gcloud firestore indexes composite create`.

## Honest scoping

- The protocol adapter accepts ACP-shaped and UCP-shaped messages; spec conformance is out of scope.
- AP2 is represented as a mandate with cap, scope, expiry and a signature presence check; cryptographic verification is stubbed.
- The buyer's agent is our own scripted agent (a Claude call under a mandate) so the demo is deterministic; real agents would connect through the same adapter.
- Retailer systems are mock data in Firestore; in production the MCP server sits next to the retailer's PIM and ERP. `create_order` records list prices; the negotiated bundle total is carried on the order event.
- Semantic search narrows 32 SKUs to 15 candidates; the same path scales to a full catalogue.
- Gates are deterministic and run regardless of model output; they are the fail-safe, not the primary control.
- Replay mode streams a recorded run. The live demo runs live first; if replay is used, we say so.

## Declared resources

Anthropic API (Claude Haiku 4.5 by default; Claude Opus 5 selectable via `MACS_MODEL`) for the intent decoder, proposal engine and simulated buyer agent;
Vertex AI text-embedding-005; FastAPI, Pydantic, FastMCP, Uvicorn, sse-starlette; LangGraph;
Vue 3, Vite; Firestore (native vector search); Google Cloud Run, Cloud Build, Artifact Registry,
Secret Manager, Firebase Hosting; mock podcasting catalogue generated by the team; AI coding
assistants (Claude Code) used with team oversight, as permitted by the rulebook.
