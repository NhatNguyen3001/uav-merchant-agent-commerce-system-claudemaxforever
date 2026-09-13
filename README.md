# MACS: Merchant Agent Commerce System

A retailer-side service that sells to autonomous AI shopping agents.

MACS receives a request from a buyer's agent, verifies the agent and its spending mandate, decodes the request into a structured intent, retrieves matching products by semantic search, composes a justified bundle, negotiates within the merchant's limits, and places the order through the retailer's existing systems. Language models reason about the request; deterministic gates decide what is allowed.

Built for the UAVS Hackathon 2026 by Team ClaudeMax Forever, in response to the problem statement set by FPT Australasia.

Live console: https://merchant-agent-commerce-system.web.app

## Contents

1. [Overview](#overview)
2. [Demonstration](#demonstration)
3. [Architecture](#architecture)
4. [Governance gates](#governance-gates)
5. [Console](#console)
6. [Getting started](#getting-started)
7. [Configuration](#configuration)
8. [API reference](#api-reference)
9. [Project structure](#project-structure)
10. [Testing](#testing)
11. [Deployment](#deployment)
12. [Performance](#performance)
13. [Known limitations](#known-limitations)
14. [Third-party resources](#third-party-resources)

## Overview

Shoppers are beginning to delegate purchasing to AI assistants. Those assistants do not read banners or product photography. They need structured product data, verifiable claims, a way to negotiate, and a way to buy without a checkout page. Most retail sites are either invisible to them or easy to misread.

MACS is an add-on layer rather than a replacement storefront. It connects to the catalogue, pricing, stock, and order systems a retailer already runs and gives them a controlled entry point for machine customers.

Design priorities, in the order the brief weighted them:

1. Intent accuracy and semantic matching. The intent decoder and vector retrieval are the core of the system.
2. Technical architecture. Every price in a proposal is traceable to a tool result, and every gate decision is a fixed rule.
3. Business value. The merchant sets a discount cap and a margin floor once; the system negotiates inside them without exposing them.

## Demonstration

A single live run exercises the full pipeline:

1. A buyer's agent sends a request, for example: "I'm starting a podcast from a small apartment on a noisy street. Complete beginner. Sustainable brands only. Budget is 600 and I need everything by next weekend."
2. The inbound gate verifies the agent's credential and mandate.
3. The intent decoder returns a structured intent: goal, skill level, environment, values, hard constraints, and soft preferences.
4. Semantic search retrieves the closest products; hard filters apply the budget, delivery, and stock limits.
5. The proposal engine composes a bundle with one rationale per item and a cheaper alternative.
6. The outbound gate verifies every price and shipping figure against a tool result, enforces the discount cap and margin floor, and corrects the proposal where needed.
7. The buyer's agent counters once, the merchant re-proposes, and the buyer's agent accepts.
8. The execution gate checks the mandate and places the order. The reply states the order id, total, and delivery time.

A second run from an unregistered agent stops at the inbound gate. Both runs are recorded as replayable examples in the console, and any free-text request can be run live against one of three simulated identities.

## Architecture

```
Buyer's agent (external, simulated)
        |  ACP-shaped message
        v
+------------------+
| Protocol adapter |  maps ACP/UCP-shaped input to a MerchantRequest
+--------+---------+
         v
+------------------+  credential, mandate, injection screen
|   Inbound gate   |  deterministic
+--------+---------+
         v
+------------------+  Claude returns an Intent (forced tool call, Pydantic-validated)
|  Intent decoder  |
+--------+---------+
         v
+------------------+  semantic_search and search_products over MCP
| Proposal engine  |  Claude returns a Proposal with per-item rationale and an alternative
+--------+---------+
         v
+------------------+  grounding, prices, shipping, discount cap, margin floor, claims
|  Outbound gate   |  deterministic; corrects rather than rejects
+--------+---------+
         v
+------------------+  buyer's agent counters once; merchant re-proposes
|    Negotiate     |  at most two rounds
+--------+---------+
         v
+------------------+  buyer acceptance, mandate signature, expiry, scope, spend cap
|  Execution gate  |  deterministic
+--------+---------+
         v
+------------------+  create_order over MCP, written to Firestore
| Retailer systems |
+------------------+
```

### Components

**Orchestration.** A flat LangGraph state graph. Each node is an async function over a single typed state. Conditional edges handle blocked paths and the two-round negotiation loop. Source: `backend/macs/graph/`.

**Retailer systems as MCP tools.** A FastMCP server exposes `search_products`, `semantic_search`, `get_product`, `get_price`, `get_shipping`, and `create_order`. The graph calls them through an in-process MCP client. Every price, stock level, and delivery figure in a proposal carries the id of the tool result it came from. Only `create_order` writes.

**Semantic search.** Products are embedded with Vertex AI `text-embedding-005` and the vectors are stored on their Firestore documents. At query time the decoded intent is embedded and Firestore native vector search returns the nearest products by cosine distance. Hard filters then narrow the set by budget, delivery days, and stock. Run time and cost do not grow with catalogue size, because the model only ever sees the shortlisted candidates.

**Language model calls.** Three roles use Claude: the intent decoder, the proposal engine, and the simulated buyer's agent. Each call is a forced tool call validated by a Pydantic model. Malformed output is fed back to the model once as a tool error. Hard merchant rules are never included in a prompt.

**Negotiation policy.** The buyer's agent's action each round is decided in code per identity; the model writes the wording. One registered identity counters once and then accepts, the other accepts the first offer. This keeps live demonstrations predictable.

**Event stream.** Every step emits a typed event (message, intent, tool, gate, stage, proposal, decision, order) with a monotonic id. Events stream to the console over Server-Sent Events and are persisted per run in Firestore, which is what history and replay read.

**Storage.** Firestore holds the catalogue, merchant rules, mandates, credentials, injection patterns, runs, events, and orders.

**Catalogue.** Two sources merged at seed time: 32 hand-built podcasting products that the demonstration resolves against, and 499 scraped Amazon listings (electronics, health and beauty, Kindle books) enriched by `backend/enrich.py`. Enrichment asks Claude Haiku 4.5, ten listings per call, for a product type, who it suits, outcome tags, a one-sentence description, durability, compatibility, and any certification present in the title. Fields a scrape cannot provide are assigned by rule: cost is 60 percent of list price, shipping days are parsed from the delivery text with a default of 3, and stock is 25.

## Governance gates

Validate what comes in, govern what goes out, authorise what gets executed.

| Gate | Checks | Outcome on failure |
|---|---|---|
| Inbound | Credential exists and is active. Mandate exists, belongs to the agent, and is unexpired. Free text contains no known injection phrase. | Blocked. The merchant replies with the reason. |
| Outbound | Every item cites a tool result from this run. Item prices match list prices. Shipping meets the deadline and items are in stock. Bundle discount is within the cap. Margin is above the floor. Sustainability claims apply only to certified products. The alternative is priced within the cap. | Corrected and re-issued, or blocked when an item is ungrounded, late, or out of stock. |
| Execution | The buyer's agent accepted the final proposal. Mandate signature is present and the mandate is unexpired. Items are within the mandate scope. Total is within the spend cap when one is set. | Blocked. No order is written. |

The hard rules (`max_discount_pct`, `min_margin_pct`) are read only by the gates. The retailer can change them in the console without touching a prompt, and a buyer's agent cannot extract them.

## Console

The console is built for the retailer's e-commerce manager and for anyone seeing the system for the first time. The buyer's agent is external traffic that the console simulates.

**Conversation panel.** Type what the buyer's agent asks for, choose an identity, and run. Three identities are available: a registered buyer that negotiates once, a registered buyer that accepts the first offer, and an unregistered agent that is refused. The exchange between the buyer's agent and the merchant agent appears as a chat, and the merchant closes every conversation with the outcome. Five example requests are provided.

**Pipeline panel.** A progress bar across the seven stages, an outcome sentence, and one collapsible row per pipeline event: gate verdicts with before-and-after corrections, the decoded intent, grouped tool calls with latency, proposals with rationale and SKU, the buyer's decision each round, and the order. Rows are titled in plain language. The panel is hidden by default and opens with one click.

**Merchant rules.** Edit the discount cap, margin floor, and negotiation style, save, and run again.

**History.** Replay any past run or either recorded example. Delete your own runs; the examples are protected.

All amounts are in US dollars.

## Getting started

### Prerequisites

- Docker Desktop
- An Anthropic API key
- Google Application Default Credentials for a Google Cloud project with Firestore in native mode (`gcloud auth application-default login`)

### Run with Docker Compose

```bash
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

The console is served at http://localhost:8080 and the API health check at http://localhost:8000/health. If port 8080 is in use, set `WEB_PORT=8081`.

### Run locally without cloud access

Recorded model outputs and an in-memory store allow development with no API key and no cloud project.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
FAKE_LLM=1 .venv/Scripts/python -m uvicorn macs.app:app --port 8000

cd ../frontend
npm install
npm run dev
```

### Seed a Firestore project

```bash
cd backend
.venv/Scripts/python seed.py --project <project-id> --catalogue catalogue.json --catalogue catalogue_scraped.json
gcloud firestore indexes composite create --project=<project-id> --collection-group=catalogue \
  --query-scope=COLLECTION --field-config='vector-config={"dimension":"768","flat":"{}"},field-path=embedding'
```

Seeding loads governance data, embeds and writes the catalogue, and loads the recorded examples. Use `--golden-only` to reload only the examples.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude access | Required for live runs |
| `GOOGLE_CLOUD_PROJECT` | Firestore and Vertex AI project | Unset; a seeded in-memory store is used |
| `MACS_MODEL` | Claude model for all three roles | `claude-sonnet-5` |
| `FAKE_LLM` | `1` returns recorded model outputs and makes no API calls | `0` |
| `REPLAY` | `1` streams recorded runs instead of executing the graph | `0` |
| `WEB_PORT` | Host port for the console under Docker Compose | `8080` |

## API reference

| Method and path | Description |
|---|---|
| `POST /api/runs` | Start a run. Body `{agent_id, query}` for a typed request, or `{scenario}` for a canned scenario or a past run id to replay. Returns `{run_id}`. |
| `GET /api/runs/{run_id}/events` | Server-Sent Events stream of the run. |
| `GET /api/runs` | Past runs with summaries, recorded examples first. |
| `GET /api/runs/{run_id}` | Full event list for a run. |
| `DELETE /api/runs/{run_id}` | Delete a run. Recorded examples return 403. |
| `DELETE /api/runs` | Delete every run except the recorded examples. |
| `GET /api/agents` | Identities the console can simulate. |
| `GET /api/config/rules` | Read merchant rules. |
| `PUT /api/config/rules` | Update merchant rules. |
| `GET /health` | Liveness and active project. |

## Project structure

```
backend/
  macs/
    app.py            FastAPI endpoints, SSE streaming, replay, startup cleanup
    llm.py            Claude wrapper: forced tool calls, validation, one retry
    models.py         Pydantic contracts for every event and object
    store.py          Store interface: Firestore in production, in-memory for tests
    mcp_server.py     FastMCP retailer tools
    emitter.py        Run registry and event emitter
    scenarios.py      Canned scenarios and simulated identities
    graph/            LangGraph state, nodes, gates, and edges
    fixtures/         Recorded model outputs for FAKE_LLM mode
  seed.py             Load data/ into Firestore, embed the catalogue, load the examples
  enrich.py           Turn scraped listings into catalogue records with Claude Haiku 4.5
  record.py           Run a scenario live and save it as a replayable example
  tests/              pytest suite
frontend/             Vue 3 console (Vite)
data/                 Catalogues, merchant rules, mandates, credentials, injection patterns, examples
docs/superpowers/     Design specification and implementation plan
docker-compose.yml    Local packaging
deploy.sh             Cloud Run and Firebase Hosting deployment
```

## Testing

```bash
cd backend
.venv/Scripts/python -m pytest
```

The suite contains 65 tests covering the data contracts, the store, seed data, the event emitter, the LLM wrapper, the MCP tools, all three gates, every graph node, both scenarios end to end through LangGraph, and the HTTP API including streaming, replay, deletion, and interrupted-run cleanup. Tests use recorded model outputs and an in-memory store and make no network calls.

## Deployment

`deploy.sh` performs the full release:

1. Builds the backend image with Cloud Build and pushes it to Artifact Registry.
2. Grants the Cloud Run service account access to Firestore, Vertex AI, and the API key secret.
3. Deploys the service to Cloud Run in `australia-southeast1` with one warm instance.
4. Builds the console with the Cloud Run URL and publishes it to Firebase Hosting.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
bash deploy.sh
```

The console calls Cloud Run directly. Firebase Hosting buffers rewritten responses, which would break the Server-Sent Events stream; the `/api/**` rewrite remains as a fallback for plain requests.

## Performance

A full live run takes about 30 seconds on Claude Sonnet 5. The two proposal compositions dominate; intent decoding takes about 4 seconds and each buyer reply about 3. Two design decisions came from measurement:

- Structured outputs and strict tool use both rely on constrained decoding, which generated at about 40 tokens per second on the nested proposal schema. A non-strict forced tool call runs at about 95 tokens per second. The wrapper uses the faster path, validates with Pydantic, tolerates JSON-encoded strings and bare scalars, and returns a validation error to the model once.
- The first semantic search after a process start costs about 5 seconds for the Vertex AI access token. Subsequent searches complete in under half a second.

## Known limitations

- The protocol adapter accepts ACP-shaped and UCP-shaped messages. Full specification conformance is out of scope.
- AP2 is represented as a mandate with a spend cap, scope, expiry, and a signature presence check. Cryptographic verification is not implemented.
- The buyer's agent is a scripted Claude call under a mandate with a fixed negotiation policy per identity. Real agents would connect through the same adapter.
- Retailer systems are mock data in Firestore. In production the MCP server would sit beside the retailer's product information and order management systems.
- The outbound gate enforces merchant rules and delivery promises. It does not enforce the buyer's stated budget; that remains the buyer's agent's decision.
- Scraped catalogue listings carry rule-assigned cost, stock, and shipping days.
- Gates are deterministic and run regardless of model output. They are the fail-safe, not the primary control.
- Replay streams a recorded run. Live demonstrations run live; if a replay is shown, it is labelled as an example.

## Third-party resources

Declared in accordance with the hackathon rulebook.

| Category | Resources |
|---|---|
| Language models | Anthropic Claude Sonnet 5 (default, selectable via `MACS_MODEL`) for the intent decoder, proposal engine, and simulated buyer's agent; Claude Haiku 4.5 for catalogue enrichment |
| Embeddings and search | Vertex AI `text-embedding-005`; Firestore native vector search |
| Backend | Python 3.11, FastAPI, Pydantic, FastMCP, LangGraph, Uvicorn, sse-starlette |
| Frontend | Vue 3, Vite, IBM Plex Sans, IBM Plex Mono, and JetBrains Mono via Fontsource |
| Cloud | Google Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Firestore, Firebase Hosting |
| Data | A podcasting catalogue authored by the team; publicly listed Amazon product data, enriched as described above |
| Tooling | AI coding assistants (Claude Code) used under team review, as permitted by the rulebook |
