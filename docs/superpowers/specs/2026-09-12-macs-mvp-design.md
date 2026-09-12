# Merchant Agent Commerce System (MACS) — MVP Design

Date: 2026-09-12
Team: ClaudeMax Forever, UAVS Hackathon 2026, FPT Australasia brief
Status: approved in brainstorming, pending written review

This spec is the build reference for the Round 2 MVP. It supersedes the
storage and retrieval choices in the Round 2 technical plan (Firestore
everywhere from day one, semantic search in day one scope) and keeps
everything else from that plan.

## 1. Goal

A retailer-side system that receives a complex query from an external AI
buyer agent, verifies the agent, decodes the buyer's intent into a
structured object, matches the catalogue semantically, composes a
justified product bundle, negotiates within merchant limits, and places
the order through the retailer's systems via MCP tools.

Principle: the AI reasons, rules decide. Two LLM nodes and one LLM buyer
agent produce structured output. Three deterministic gates validate what
comes in, govern what goes out, and authorise what gets executed. Hard
rules never enter the model context.

Judging weights, in order: intent accuracy and semantic matching,
technical architecture, business value. UI polish is low priority.

Out of scope: consumer-facing shopping assistant, human UI/UX
optimisation, physical logistics, protocol spec conformance,
cryptographic mandate verification.

## 2. Decisions made in brainstorming

| Decision | Choice |
|---|---|
| Build scope | Whole MVP, solo build with AI assistance |
| Orchestration | LangGraph flat graph with nodes as plain functions |
| Retailer systems | FastMCP server, in-process client, tools read Firestore |
| Storage | Firestore only, from day one. No SQLite. |
| Semantic search | Firestore native vector search, Vertex AI `text-embedding-005` |
| Chat history | Every event, including messages, persisted per run in Firestore |
| Replay | Reads golden and past runs from Firestore |
| Frontend | Vue 3 + Vite, no UI library |
| Hosting | Cloud Run (australia-southeast1) + Firebase Hosting, day one |
| GCP project | `merchant-agent-commerce-system`, Firestore native in australia-southeast1 |
| LLM | Anthropic API, tool use forced, temperature 0, `FAKE_LLM=1` for tests |
| Tests | pytest, Firestore emulator, fake LLM. Frontend untested. |

## 3. Repository layout

```
backend/
  app/            FastAPI app: routes, SSE, run store, config
  graph/          LangGraph state, nodes, edges, emitter (only importer of langgraph)
  mcp_server/     FastMCP server, Firestore queries, embedder
  buyer/          scripted buyer agent (LLM decision, ACP-shaped messages)
  fixtures/       canned LLM outputs for FAKE_LLM mode
  tests/
  llm.py          Anthropic wrapper + fake mode
  models.py       Pydantic contracts
  seed.py         loads data/ into Firestore, embeds catalogue
  Dockerfile      python:3.12-slim
  pyproject.toml
frontend/         Vue 3 + Vite; src/components, src/composables, one CSS file
data/
  catalogue.json  merchant_rules.json  mandates.json  credentials.json
  injection_patterns.json
  replay/happy_path.json  replay/rejected_agent.json   (recorded golden runs)
docker-compose.yml
deploy.sh         Cloud Build -> Artifact Registry -> Cloud Run, then firebase deploy
firebase.json     hosting with /api/** rewrite to Cloud Run
.firebaserc
README.md
```

## 4. Runtime

One backend process. FastAPI starts, constructs the FastMCP server object,
and graph nodes call tools through the in-process FastMCP client. No
second process, no MCP network transport.

Firestore access uses Application Default Credentials locally and the
Cloud Run service account when hosted. Local development on Python 3.11
(Anaconda); the Docker image uses 3.12. No 3.12-only syntax.

Environment variables:

| Var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude calls |
| `GOOGLE_CLOUD_PROJECT` | `merchant-agent-commerce-system` |
| `FAKE_LLM` | `1` returns canned outputs from `backend/fixtures/`; embedder becomes keyword overlap |
| `REPLAY` | `1` makes `POST /api/runs` stream a golden run instead of executing the graph |
| `FIRESTORE_EMULATOR_HOST` | set by tests |

Dependencies, backend: fastapi, uvicorn, pydantic v2, anthropic, langgraph,
fastmcp, sse-starlette, google-cloud-firestore, google-cloud-aiplatform,
pytest. Frontend: vue, vite.

## 5. Firestore collections

| Collection | Document shape |
|---|---|
| `catalogue/{sku}` | sku, name, type, list_price, cost, stock, ship_days, specs, suited_for[], sustainability{materials, certifications, brand_practice}, durability, compatibility[], outcome_tags[], embedding (vector) |
| `merchant_rules/current` | soft{negotiation_style, allowed_claims, bundling, category_restrictions, pricing_guidance}, hard{max_discount_pct, min_margin_pct, category_overrides} |
| `mandates/{mandate_id}` | mandate_id, agent_id, spend_cap, currency, scope, expires_at, signature |
| `credentials/{agent_id}` | agent_id, issuer, status, created_at |
| `injection_patterns/current` | phrases[] |
| `runs/{run_id}` | run_id, scenario, started_at, finished_at, status (running, finished, failed), is_golden, summary{order_status, bundle_price, gate_verdicts} |
| `runs/{run_id}/events/{id}` | one event envelope per document, id zero-padded for ordering |
| `orders/{order_id}` | order_id, skus[], total, mandate_id, status, created_at |

`seed.py` is idempotent: it overwrites catalogue, rules, mandates,
credentials, patterns, and the two golden runs, and leaves live runs and
orders alone. It embeds each product's text rendering (name, type,
suited_for, sustainability, outcome_tags) and stores the vector. One
vector index on `catalogue.embedding` (cosine, 768 dimensions) is created
by a documented gcloud command.

Mock catalogue: 30 to 50 podcasting SKUs across microphone, audio
interface, headphones, boom arm, pop filter, acoustic panels. Values
chosen so the demo scenario in section 10 resolves to the stated prices.

## 6. Contracts

### 6.1 Event envelope

```
{ id: int (starts at 1, +1 per event within a run),
  run_id: str, ts: ISO 8601 with +10:00 offset,
  lane: merchant | a2a | system,
  type: message | tool | gate | stage | intent | proposal | order,
  payload: object }
```

Lane rendering: merchant -> left console, a2a -> right transcript,
system -> top strip (stage events only).

### 6.2 Payloads

| type | fields |
|---|---|
| message | from: buyer_agent \| merchant_agent; text |
| tool | name; args; result_summary; latency_ms; tool_result_id |
| gate | gate: inbound \| outbound \| execution; verdict: pass \| blocked \| corrected; reason; before (object or null); after (object or null) |
| stage | stage: protocol_adapter \| inbound_gate \| intent_decoder \| proposal_engine \| outbound_gate \| execution_gate \| retailer_systems; status: idle \| running \| passed \| blocked; note |
| intent | goal; skill_level; environment[]; values[]; hard_constraints{budget_max, deliver_by_days}; soft_preferences[]; constraint_count |
| proposal | items[{sku, name, price, rationale, satisfies[], grounded_on[]}]; bundle_price; discount_pct; intent_coverage; alternative{sku, name, bundle_price, tradeoff} or null; expires_at |
| order | order_id; skus[]; total; mandate_id; status: placed \| rejected |

Rules: every gate event is immediately followed by a stage event for the
same stage. A run ends with a stage event on `retailer_systems` (passed)
or on whichever stage blocked. Chat history is the ordered `message`
events of a run.

### 6.3 Internal models (Pydantic, `backend/models.py`)

- `MerchantRequest(request_id, protocol: acp|ucp, agent_id, mandate_id, raw_query, conversation: list[Message])`
- `Intent(goal, skill_level, environment, values, hard_constraints: HardConstraints(budget_max, deliver_by_days), soft_preferences)`
- `ToolResultRef(tool_result_id, sku)`
- `ProposalItem(sku, name, price, rationale, satisfies, grounded_on: list[ToolResultRef])`
- `Proposal(items, bundle_price, discount_pct, intent_coverage, alternative: Proposal | None, expires_at)`
- `BuyerDecision(action: accept|counter, message, counter_budget: float | None)`
- `Order(order_id, skus, total, mandate_id, status)`
- `Event(id, run_id, ts, lane, type, payload)`

### 6.4 HTTP endpoints

| Endpoint | Behaviour |
|---|---|
| `POST /api/runs` body `{scenario}` | scenario is `happy_path`, `rejected_agent`, or a past `run_id`. Creates the run doc, starts the graph in a background task (or a replay task when `REPLAY=1` or scenario is a run id), returns `{run_id}` |
| `GET /api/runs/{run_id}/events` | SSE. Live run: replays the in-memory buffer then tails. Finished run: streams events from Firestore with a 300 ms gap. Closes after the terminal stage event |
| `GET /api/runs` | list of run summaries, golden runs first, newest next |
| `GET /api/runs/{run_id}` | full event list |
| `GET /api/config/rules` | current merchant rules |
| `PUT /api/config/rules` | replace the rules document; body validated by Pydantic |
| `GET /health` | `{status: ok, project}` |

## 7. Graph

### 7.1 State

TypedDict with keys: request, credential, mandate, intent, candidates,
proposal, gate_results, negotiation_round, buyer_reply, order, blocked.
Nodes take the state and return a partial dict. An `Emitter` bound to
the run is held outside the state and passed to nodes via closure. It
assigns ids, writes each event to the in-memory queue and to Firestore
in the same call, and provides `gate(...)` which emits the gate event and
the paired stage event.

### 7.2 Edges

```
START -> protocol_adapter -> inbound_gate
inbound_gate -> END                 if blocked
inbound_gate -> decode_intent -> match_catalogue -> compose_proposal -> outbound_gate
outbound_gate -> END                if blocked
outbound_gate -> negotiate
negotiate -> compose_proposal       if buyer countered and negotiation_round < 2
negotiate -> execution_gate         otherwise
execution_gate -> END
```

### 7.3 Nodes

- `protocol_adapter`: maps the scenario's ACP-shaped message into `MerchantRequest`. Emits the buyer message and a stage event.
- `inbound_gate`: deterministic. Loads credential and mandate. Blocks on unknown agent, credential status not active, missing or expired mandate, or an injection phrase (case-insensitive) in free-text fields.
- `decode_intent`: one Claude call, forced tool `record_intent` with the Intent schema. Validates, computes `constraint_count`, emits intent event.
- `match_catalogue`: builds a query string from the intent. Calls `semantic_search(query, k=15)`, then `search_products` with budget and ship-day filters over those SKUs. Each tool call is emitted with `tool_result_id`, args, summary, latency. Candidates carry their tool result ids.
- `compose_proposal`: one Claude call. Context: soft rules, intent, candidates with list_price and cost, and on round two the buyer's counter message. Forced tool `record_proposal`. Each item must cite a `grounded_on` id present in candidates. Emits proposal event and a merchant message.
- `outbound_gate`: deterministic. Checks item price and stock against the grounded results, bundle discount against `max_discount_pct`, margin against `min_margin_pct`, claims in rationale against `allowed_claims`, ship days against `deliver_by_days`. Verdict `pass`, or `corrected` with before/after and the proposal rewritten to the caps, or `blocked` only when an item cites a missing tool result.
- `negotiate`: buyer agent turn. One Claude call for the buyer with the proposal and its mandate, forced tool `buyer_decision`. Emits the buyer message. In fake mode round one counters and round two accepts.
- `execution_gate`: deterministic. Checks bundle total against mandate spend_cap, scope, expiry, and signature presence. On pass calls `create_order` and emits order `placed`; otherwise emits order `rejected`. Emits `retailer_systems` stage event last.

Negotiation: hard stop after two rounds. On round two the merchant
accepts a counter within cap, otherwise restates the corrected proposal as
final and offers the alternative if budget is the issue.

## 8. LLM wrapper and MCP tools

`backend/llm.py` exposes `call_tool(system, messages, tool_schema) -> dict`
and `embed(texts) -> list[list[float]]`. Real mode: Anthropic with
`tool_choice` forced to the single tool, temperature 0, one retry with
short backoff; Vertex AI `text-embedding-005` for embeddings. Fake mode:
canned dicts from `backend/fixtures/{tool_name}_{scenario}_{round}.json`
and keyword-overlap embeddings. Every model output is validated by
Pydantic before entering state; a validation failure fails the run.

FastMCP tools, all in `backend/mcp_server/`, all reading Firestore:

| Tool | Behaviour |
|---|---|
| `search_products(filters)` | type, max_price, max_ship_days, suited_for, sku_in |
| `semantic_search(query_text, k)` | embed query, Firestore `find_nearest` cosine, returns sku, name, distance |
| `get_product(sku)` | full document |
| `get_price(sku)` | list_price, cost |
| `get_shipping(sku)` | ship_days, stock |
| `create_order(skus, mandate_id)` | writes `orders/{order_id}`, returns order |

Only `create_order` writes.

## 9. Frontend

Vue 3 + Vite. `useRun(runId)` opens an EventSource and appends events to
a reactive array. Three components filter that array:

- `PipelineStrip.vue`: seven stages; state is the latest stage event per stage; note under each.
- `MerchantConsole.vue`: rules form bound to `/api/config/rules`; scenario picker listing the two scenarios and past runs; result card derived from the latest proposal, gate, and order events (bundle, intent coverage, margin retained, gate verdicts, order status).
- `Transcript.vue`: a2a events in order, rendered by type: message, tool row, gate block, intent card, proposal with items and alternative, order block.

No business logic in the frontend. One CSS file. Colours: idle grey,
running blue, passed green, blocked red.

## 10. Demo scenarios

Happy path: query "starting a podcast, small apartment on a noisy
street, complete beginner, sustainable brands only, budget 600, needed by
next weekend". Agent buyer-001, mandate cap 600, scope audio equipment,
expires end of day. Rules: max discount 15, min margin 20, bundling
allowed, claims certified only. Intent decodes to six constraints. Bundle:
dynamic mic, USB interface, recycled-shell headphones, boom arm. Model
proposes 22 percent discount, outbound gate corrects to 15, bundle 588.
Alternative: previous-gen interface bundle at 541. Buyer counters once,
then commits. Execution gate passes, order placed.

Rejected agent: buyer-999 has no credential; inbound gate blocks; strip
stops red.

Both scenarios are recorded once from live runs into `data/replay/` and
seeded as golden runs.

## 11. Error handling

Any exception in a node marks the run `failed`, emits a stage event with
status `blocked` and the error message on the current stage, and closes
the SSE stream. Anthropic and Vertex calls get one retry. Nothing else is
retried. Firestore write failures propagate and fail the run.

## 12. Testing

pytest with `FAKE_LLM=1` and `FIRESTORE_EMULATOR_HOST` set (firebase-tools
emulator). Tests seed the emulator from `data/` in a fixture.

- Inbound gate: unknown agent, inactive credential, expired mandate, injection phrase, happy case.
- Outbound gate: pass, discount correction math, margin floor, missing grounded ref blocks, ship-day violation.
- Execution gate: within cap, over cap, expired, missing signature.
- Emitter: ids increment, gate events are followed by paired stage events.
- MCP tools: filters, keyword semantic fallback, create_order writes.
- LLM nodes: fake output validates; malformed fixture fails the run cleanly.
- End to end: both scenarios produce the golden event sequence (types and gate verdicts, not timestamps).

## 13. Deployment

Local: `docker compose up` runs api on 8000 with the ADC file mounted
and web as a Vite build behind nginx proxying `/api`. This is what
judges reproduce.

Hosted: `deploy.sh` builds with Cloud Build, pushes to Artifact Registry,
deploys to Cloud Run in australia-southeast1 with `ANTHROPIC_API_KEY`
from Secret Manager and min instances 1, then runs `firebase deploy` for
Hosting with `/api/**` rewritten to the Cloud Run service.

## 14. Declared resources

Anthropic API (Claude), Vertex AI text-embedding-005, FastAPI, Pydantic,
FastMCP, Uvicorn, sse-starlette, LangGraph, Vue 3, Vite, Firestore
(native vector search), Cloud Run, Cloud Build, Artifact Registry, Secret
Manager, Firebase Hosting, Firestore emulator for tests, team-generated
mock catalogue, AI coding assistants with team oversight.

## 15. README honesty language

Protocol adapter accepts ACP-shaped and UCP-shaped messages, spec
conformance out of scope. AP2 is a mandate with cap, scope, expiry, and
signature presence; cryptographic verification is stubbed. The buyer's
agent is our own scripted agent for determinism. Retailer systems are
mock data in Firestore; in production the MCP server sits next to PIM
and ERP. Semantic search narrows 50 SKUs to 15 candidates; the same path
scales to a full catalogue. Gates are deterministic and run regardless of
model output; they are the fail-safe, not the primary control.
