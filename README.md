# MACS — Merchant Agent Commerce System

**UAVS Hackathon 2026 · Team ClaudeMax Forever · Problem statement by FPT Australasia**

Live demo: https://merchant-agent-commerce-system.web.app

MACS is a retailer-side layer that sells to autonomous AI shopping agents. When a buyer's agent arrives with a complex, multi-constraint request, MACS verifies the agent and its spending mandate, decodes the request into a structured intent, retrieves matching products by semantic search, composes a justified bundle, negotiates within the merchant's limits, and places the order through the retailer's own systems. The AI reasons; deterministic gates decide.

## Contents

- [Why](#why)
- [What the demo shows](#what-the-demo-shows)
- [Architecture](#architecture)
- [The three gates](#the-three-gates)
- [Console](#console)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API](#api)
- [Repository layout](#repository-layout)
- [Testing](#testing)
- [Deployment](#deployment)
- [Performance notes](#performance-notes)
- [Scope and honest limitations](#scope-and-honest-limitations)
- [Declared resources](#declared-resources)

## Why

Shoppers increasingly delegate purchasing to AI assistants. Those assistants do not read banners or product photography; they need structured data, verifiable claims, a way to negotiate, and a way to buy without a checkout page. Most retail sites are invisible to them or easy to misread. Retailers cannot rebuild their storefronts for machines, so MACS is an add-on layer: it connects to the catalogue, pricing, stock, and order systems that already exist, and gives them a door for machine customers.

Judging priorities for this brief, in order of weight, were intent accuracy and semantic matching, technical architecture, and business value. MACS is built around those priorities: the intent decoder and semantic retrieval are the headline, the gates are the fail-safe, and the console stays minimal.

## What the demo shows

One live run covers every step of the brief's winning demonstration:

1. A buyer's agent arrives with a request such as *"I'm starting a podcast from a small apartment on a noisy street. Complete beginner. Sustainable brands only. Budget is 600 and I need everything by next weekend."*
2. The inbound gate verifies the agent's credential and mandate.
3. The intent decoder produces a structured intent: goal, skill level, environment, values, hard constraints, soft preferences.
4. Semantic search retrieves the closest products from the catalogue; hard filters apply budget and delivery limits.
5. The proposal engine composes a bundle with one rationale per item and a cheaper alternative.
6. The outbound gate checks every price against a tool result and enforces the discount cap and margin floor, correcting the proposal if needed.
7. The buyer's agent counters once; the merchant re-proposes; the buyer accepts or declines.
8. The execution gate checks the mandate and places the order.

A second run with an unregistered agent stops at the inbound gate. Both runs are recorded as replayable examples, and any query can be typed into the console and run live.

## Architecture

```
Buyer's agent (external, simulated)
        │  ACP-shaped message
        ▼
┌─────────────────┐
│ Protocol adapter │  maps ACP/UCP-shaped input to MerchantRequest
└────────┬────────┘
         ▼
┌─────────────────┐   credentials, mandate, schema, injection screen
│  Inbound gate    │   deterministic
└────────┬────────┘
         ▼
┌─────────────────┐   Claude → Intent (forced tool call, Pydantic-validated)
│ Intent decoder   │
└────────┬────────┘
         ▼
┌─────────────────┐   semantic_search + search_products over MCP
│ Proposal engine  │   Claude → Proposal with per-item rationale and alternative
└────────┬────────┘
         ▼
┌─────────────────┐   grounding, discount cap, margin floor, claims, shipping
│  Outbound gate   │   deterministic; corrects rather than rejects
└────────┬────────┘
         ▼
┌─────────────────┐   buyer's agent counters once; merchant re-proposes
│   Negotiate      │   at most two rounds
└────────┬────────┘
         ▼
┌─────────────────┐   buyer acceptance, mandate scope, expiry, signature, cap
│ Execution gate   │   deterministic
└────────┬────────┘
         ▼
┌─────────────────┐   create_order over MCP → Firestore
│ Retailer systems │
└─────────────────┘
```

**Orchestration.** A flat LangGraph state graph. Every node is a plain async function over one TypedDict; conditional edges handle the blocked paths and the two-round negotiation loop. All graph code lives in `backend/macs/graph/`.

**Retailer systems as MCP tools.** A FastMCP server exposes `search_products`, `semantic_search`, `get_product`, `get_price`, `get_shipping`, and `create_order`. The graph calls them through an in-process MCP client, so every price, stock level, and delivery figure in a proposal is traceable to a tool result id, and only `create_order` writes.

**Semantic search.** Products are embedded with Vertex AI `text-embedding-005` and stored on their Firestore documents. At query time the decoded intent is embedded and Firestore's native vector search returns the nearest products by cosine distance. Hard filters then narrow by budget and delivery days.

**Event stream.** Every step emits an event (message, intent, tool, gate, stage, proposal, decision, order) with a monotonic id. Events stream to the console over Server-Sent Events and are persisted per run in Firestore, which is what history and replay read.

**Storage.** Firestore only: catalogue, merchant rules, mandates, credentials, injection patterns, runs, events, and orders.

**Catalogue.** Two sources, merged at seed time: a hand-built set of 32 podcasting SKUs that the demo scenario resolves against, and 499 scraped Amazon listings (electronics, health and beauty, Kindle books) enriched by `backend/enrich.py`. Enrichment asks Claude Haiku 4.5, ten listings per call, for a product type, who it suits, outcome tags, a one-sentence description, durability, compatibility, and any certification literally present in the title. Fields a scrape cannot provide are assigned by rule and stated here: cost is 60 percent of list, ship days are parsed from the delivery text (default 3), stock is 25. The full 499-product enrichment took 50 calls and about 90 seconds.

## The three gates

Validate what comes in, govern what goes out, authorise what gets executed.

| Gate | Checks | On failure |
|---|---|---|
| Inbound | credential exists and is active; mandate exists, belongs to the agent, and is unexpired; free text contains no injection pattern | blocked |
| Outbound | every item cites a tool result from this run; item prices match list prices; ship days meet the deadline; bundle discount within the cap; margin above the floor; sustainability claims only for certified products; alternative priced within the cap | corrected, or blocked if ungrounded |
| Execution | buyer's agent accepted the final proposal; mandate signature present; mandate unexpired; items within mandate scope (`any`, or `audio_equipment` for the audio-only mandate); total within the spend cap when one is set | blocked, no order |

The hard rules (`max_discount_pct`, `min_margin_pct`) are read only by the gates and never enter a model prompt. A buyer's agent cannot extract them, and the retailer can change them in the console without touching a prompt.

## Console

The console is built for the retailer's e-commerce manager, not the shopper. The buyer's agent is external traffic that the console simulates.

- **Conversation panel.** Type what an incoming agent says, pick its identity (registered, expired mandate, unregistered), and watch the exchange between the buyer's agent and the merchant agent. The merchant closes every conversation with an outcome.
- **Pipeline panel.** A progress bar across the seven stages, an outcome line, and one collapsible row per pipeline event: gate verdicts with before/after corrections, the decoded intent, grouped tool calls with latency, proposals with rationale and SKU, the buyer's decision each round, and the order. Hidden by default; one click shows it.
- **Merchant rules.** Edit the discount cap, margin floor, and negotiation style, save, and run again.
- **History.** Replay any past run or the two recorded examples. Delete your own runs; the examples are protected.

## Quick start

Requirements: Docker, an Anthropic API key, and Google Application Default Credentials for a GCP project with Firestore (`gcloud auth application-default login`).

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

Console at http://localhost:8080, API health at http://localhost:8000/health. If port 8080 is taken, set `WEB_PORT=8081`.

Offline development, with recorded model outputs and an in-memory store, needs no key and no cloud project:

```bash
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
FAKE_LLM=1 .venv/Scripts/python -m uvicorn macs.app:app --port 8000
cd ../frontend && npm install && npm run dev
```

Seed a fresh Firestore project and create the vector index:

```bash
cd backend
.venv/Scripts/python seed.py --project <project-id> --catalogue catalogue.json --catalogue catalogue_scraped.json
gcloud firestore indexes composite create --project=<project-id> --collection-group=catalogue \
  --query-scope=COLLECTION --field-config='vector-config={"dimension":"768","flat":"{}"},field-path=embedding'
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude access | required for live runs |
| `GOOGLE_CLOUD_PROJECT` | Firestore and Vertex AI project | unset → seeded in-memory store |
| `MACS_MODEL` | Claude model for all three roles | `claude-sonnet-5` |
| `FAKE_LLM` | `1` returns recorded model outputs, no API calls | `0` |
| `REPLAY` | `1` streams recorded runs instead of executing the graph | `0` |
| `WEB_PORT` | host port for the console under Docker Compose | `8080` |

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/runs` | Start a run. Body `{agent_id, query}` for a typed query, `{scenario}` for a canned scenario or a past run id to replay. Returns `{run_id}`. |
| `GET /api/runs/{run_id}/events` | Server-Sent Events stream of the run's events. |
| `GET /api/runs` | Past runs with summaries; recorded examples first. |
| `GET /api/runs/{run_id}` | Full event list. |
| `DELETE /api/runs/{run_id}` | Delete a run. Recorded examples return 403. |
| `DELETE /api/runs` | Delete every run except the recorded examples. |
| `GET /api/agents` | Agent identities the console can simulate. |
| `GET` / `PUT /api/config/rules` | Read or update merchant rules. |
| `GET /health` | Liveness and active project. |

## Repository layout

```
backend/
  macs/
    app.py            FastAPI endpoints, SSE, replay, startup cleanup
    llm.py            Claude wrapper: forced tool calls, validation, retry
    models.py         Pydantic contracts for every event and object
    store.py          Store interface: Firestore (production), in-memory (tests)
    mcp_server.py     FastMCP retailer tools
    emitter.py        run registry and event emitter
    scenarios.py      canned scenarios and agent identities
    graph/            LangGraph state, nodes, gates, edges
    fixtures/         recorded model outputs for FAKE_LLM mode
  seed.py             load data/ into Firestore, embed the catalogue(s), load examples
  enrich.py           turn scraped listings into catalogue records with Haiku 4.5
  record.py           run a scenario live and save it as a replayable example
  tests/              pytest suite
frontend/             Vue 3 console
data/                 catalogue.json (32 podcasting SKUs), catalogue_scraped.json (499 enriched
                      Amazon listings), rules, mandates, credentials, injection patterns, examples
docs/superpowers/     design spec and implementation plan
docker-compose.yml    local packaging
deploy.sh             Cloud Run + Firebase Hosting deploy
```

## Testing

```bash
cd backend && .venv/Scripts/python -m pytest
```

59 tests cover the contracts, store, seed data, emitter, LLM wrapper, MCP tools, all three gates, every graph node, both scenarios end to end through LangGraph, and the HTTP API including SSE, replay, deletion, and interrupted-run cleanup. Tests use recorded model outputs and an in-memory store; they make no network calls.

## Deployment

`deploy.sh` builds the backend with Cloud Build, deploys it to Cloud Run in `australia-southeast1` with the API key from Secret Manager, grants the runtime service account access to Firestore, Vertex AI, and the secret, builds the console with the Cloud Run URL baked in, and publishes it to Firebase Hosting. The console calls Cloud Run directly because Firebase Hosting buffers rewritten responses, which would break the Server-Sent Events stream; the `/api/**` rewrite remains as a fallback for plain requests.

```bash
ANTHROPIC_API_KEY=sk-ant-... bash deploy.sh
```

## Performance notes

A full live run takes about 30 seconds on Claude Sonnet 5, the default, and about the same on Opus 5. The two proposal compositions dominate; intent decoding takes about 4 seconds and each buyer reply about 3. Two decisions came from measurement:

- Structured outputs and strict tool use both use constrained decoding, which generated at about 40 tokens per second on the nested proposal schema. A non-strict forced tool call runs at about 95 tokens per second, so the wrapper uses that, validates with Pydantic, tolerates JSON-encoded strings and bare scalars, and feeds a validation error back to the model once.
- The first semantic search after a process start costs about 5 seconds for the Vertex access token; later searches take under half a second.

## Scope and honest limitations

- The protocol adapter accepts ACP-shaped and UCP-shaped messages. Specification conformance is out of scope.
- AP2 is represented as a mandate with a cap, scope, expiry, and a signature presence check. Cryptographic verification is stubbed.
- The buyer's agent is our own scripted agent, a Claude call under a mandate, so the demo is deterministic. Real agents would connect through the same adapter.
- Retailer systems are mock data in Firestore. In production the MCP server sits beside the retailer's PIM and ERP. `create_order` records list prices; the negotiated bundle total is carried on the order event.
- The catalogue holds 531 SKUs: 32 hand-built podcasting products plus 499 enriched Amazon listings. Semantic search narrows them to 15 candidates per run, so run time and cost do not grow with catalogue size. Scraped listings carry rule-assigned cost, stock, and ship days.
- Gates are deterministic and run regardless of model output. They are the fail-safe, not the primary control.
- Replay streams a recorded run. The live demo runs live first; if replay is used, we say so.

## Declared resources

Anthropic API (Claude Sonnet 5 by default; other models selectable via `MACS_MODEL`) for the intent decoder, proposal engine, and simulated buyer's agent; Vertex AI `text-embedding-005`; FastAPI, Pydantic, FastMCP, Uvicorn, sse-starlette; LangGraph; Vue 3, Vite, IBM Plex Mono and JetBrains Mono via Fontsource; Firestore with native vector search; Google Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Firebase Hosting; a mock podcasting catalogue generated by the team; AI coding assistants (Claude Code) used with team oversight, as permitted by the rulebook.
