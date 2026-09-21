from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from macs.emitter import TZ, Emitter, RunRegistry
from macs.graph.build import new_run_id, run_scenario
from macs.llm import LLM
from macs.models import MerchantRules
from macs.scenarios import AGENTS, AGENT_BY_ID, SCENARIOS, build_input
from macs.seeddata import load_seed
from macs.store import FirestoreStore, MemoryStore, Store, VertexEmbedder

REPLAY_GAP_S = 0.3

# Each browser keeps a random session key and sends it with every request (header), or in the URL for the
# EventSource stream, which cannot send headers. Runs store only its SHA-256, never the key itself.
SESSION_HEADER = "X-MACS-Session"
_SESSION_KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def session_owner(request: Request) -> str | None:
    """Hashed session of the caller, or None when the key is missing or malformed."""
    key = request.headers.get(SESSION_HEADER) or request.query_params.get("session")
    if not key or not _SESSION_KEY.match(key):
        return None
    return hashlib.sha256(key.encode()).hexdigest()


def visible(run: dict | None, owner: str | None) -> bool:
    """The recorded examples are open to everyone; every other run only to the session that started it."""
    if run is None:
        return False
    return bool(run.get("is_golden")) or (owner is not None and run.get("owner") == owner)


class StartRun(BaseModel):
    scenario: str | None = None
    agent_id: str | None = None
    query: str | None = None


def _store_from_env() -> Store:
    """Firestore when a project is configured; otherwise a seeded in-memory store for local fake-mode runs."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return load_seed(MemoryStore())
    embedder = None if os.environ.get("FAKE_LLM") == "1" else VertexEmbedder(project)
    return FirestoreStore(project, embedder)


class _TransientStore:
    """Emitter sink for replays: events go to the registry (SSE) only, nothing is persisted."""

    def add_event(self, run_id: str, event: dict) -> None:
        return None


async def _replay_run(source_id: str, run_id: str, store: Store, registry: RunRegistry) -> None:
    em = Emitter(run_id, _TransientStore(), registry)
    try:
        for ev in store.list_events(source_id):
            em.emit(ev["lane"], ev["type"], ev["payload"])
            await asyncio.sleep(REPLAY_GAP_S)
    finally:
        registry.finish(run_id)


def mark_interrupted_runs(store: Store) -> int:
    """Runs left in 'running' by a previous process (restart, crash) can never finish; say so."""
    stale = [r for r in store.list_runs() if r.get("status") == "running"]
    for r in stale:
        r.update({"status": "interrupted", "finished_at": datetime.now(TZ).isoformat(timespec="seconds"),
                  "summary": {"order_status": "none", "bundle_price": None, "gate_verdicts": [],
                              "note": "interrupted by a server restart"}})
        store.set("runs", r["run_id"], r)
    return len(stale)


def create_app(store: Store, llm: LLM, registry: RunRegistry, replay: bool, rules_locked: bool = False) -> FastAPI:
    """`rules_locked` makes the merchant rules read-only (the hosted demo runs locked)."""
    app = FastAPI(title="MACS")
    mark_interrupted_runs(store)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    tasks: set[asyncio.Task] = set()

    def _spawn(coro):
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    @app.get("/health")
    async def health():
        return {"status": "ok", "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "local"), "replay": replay}

    @app.get("/api/config/rules")
    async def get_rules():
        return {**(store.get("merchant_rules", "current") or {}), "locked": rules_locked}

    @app.put("/api/config/rules")
    async def put_rules(rules: MerchantRules):
        if rules_locked:
            raise HTTPException(403, "Merchant rules are locked for the demo.")
        store.set("merchant_rules", "current", rules.model_dump())
        return rules

    @app.get("/api/agents")
    async def list_agents():
        return AGENTS

    @app.post("/api/runs")
    async def start_run(body: StartRun, request: Request):
        owner = session_owner(request)
        if owner is None:
            raise HTTPException(400, "missing or invalid session key")
        if body.scenario is None:
            if replay:
                # Showcase mode: recorded examples only, so a public demo cannot run up model spend.
                raise HTTPException(403, "Typed queries are switched off on this demo. Run one of the examples.")
            if not body.agent_id or not (body.query or "").strip():
                raise HTTPException(400, "provide either scenario, or agent_id and query")
            if body.agent_id not in AGENT_BY_ID:
                raise HTTPException(400, f"unknown agent_id {body.agent_id}")
            run_id = new_run_id()
            registry.open(run_id, owner)
            _spawn(run_scenario("custom", run_id, store, llm, registry,
                                input=build_input(body.agent_id, body.query.strip()), owner=owner))
            return {"run_id": run_id}
        run_id = new_run_id()
        if body.scenario in SCENARIOS and not replay:
            registry.open(run_id, owner)
            _spawn(run_scenario(body.scenario, run_id, store, llm, registry, owner=owner))
            return {"run_id": run_id}
        source = body.scenario
        if source in SCENARIOS:
            golden = [r for r in store.list_runs() if r.get("is_golden") and r.get("scenario") == source]
            if not golden:
                raise HTTPException(400, f"no golden run recorded for scenario {source}")
            source = golden[0]["run_id"]
        # Someone else's run answers exactly like an unknown one, so its existence is not revealed.
        if not visible(store.get("runs", source), owner):
            raise HTTPException(400, f"unknown scenario or run id {body.scenario}")
        registry.open(run_id, owner)
        _spawn(_replay_run(source, run_id, store, registry))
        return {"run_id": run_id, "replay_of": source}

    @app.get("/api/runs")
    async def list_runs(request: Request):
        owner = session_owner(request)
        runs = [r for r in store.list_runs() if visible(r, owner)]
        golden = [r for r in runs if r.get("is_golden")]
        others = sorted((r for r in runs if not r.get("is_golden")), key=lambda r: r.get("started_at") or "", reverse=True)
        return golden + others

    @app.delete("/api/runs/{run_id}")
    async def delete_run(run_id: str, request: Request):
        run = store.get("runs", run_id)
        if not visible(run, session_owner(request)):
            raise HTTPException(404, "run not found")
        if run.get("is_golden"):
            raise HTTPException(403, "golden example runs cannot be deleted")
        store.delete_run(run_id)
        return {"deleted": run_id}

    @app.delete("/api/runs")
    async def clear_history(request: Request):
        """Delete this session's runs; other sessions' runs and the golden examples stay."""
        owner = session_owner(request)
        victims = [r["run_id"] for r in store.list_runs() if not r.get("is_golden") and visible(r, owner)]
        for rid in victims:
            store.delete_run(rid)
        return {"deleted": len(victims)}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        if not visible(store.get("runs", run_id), session_owner(request)):
            raise HTTPException(404, "run not found")
        return store.list_events(run_id)

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(run_id: str, request: Request):
        owner = session_owner(request)
        if registry.has(run_id):
            if owner is None or registry.owner(run_id) != owner:
                raise HTTPException(404, "run not found")
        else:
            if not visible(store.get("runs", run_id), owner):
                raise HTTPException(404, "run not found")

            async def from_store():
                for ev in store.list_events(run_id):
                    yield {"event": "event", "data": json.dumps(ev)}
                    await asyncio.sleep(REPLAY_GAP_S)
            return EventSourceResponse(from_store())

        async def live():
            i = 0
            while True:
                evs = registry.events(run_id)
                while i < len(evs):
                    yield {"event": "event", "data": json.dumps(evs[i])}
                    i += 1
                if registry.is_done(run_id):
                    return
                await registry.wait(run_id)
        return EventSourceResponse(live())

    return app


def build_from_env() -> FastAPI:
    # Locked unless explicitly opened with RULES_LOCKED=0, so a forgotten setting cannot leave the demo editable.
    return create_app(_store_from_env(), LLM.from_env(), RunRegistry(), replay=os.environ.get("REPLAY") == "1",
                      rules_locked=os.environ.get("RULES_LOCKED", "1") != "0")


app = build_from_env()
