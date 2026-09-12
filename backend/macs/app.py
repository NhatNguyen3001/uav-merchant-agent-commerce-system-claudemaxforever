from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
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


async def _replay_run(source_id: str, run_id: str, store: Store, registry: RunRegistry, scenario: str) -> None:
    src0 = store.get("runs", source_id) or {}
    store.set("runs", run_id, {"run_id": run_id, "scenario": scenario, "started_at": datetime.now(TZ).isoformat(timespec="seconds"),
                              "finished_at": None, "status": "running", "is_golden": False, "summary": {},
                              "replay_of": source_id, **{k: src0[k] for k in ("agent_id", "query") if k in src0}})
    em = Emitter(run_id, store, registry)
    for ev in store.list_events(source_id):
        em.emit(ev["lane"], ev["type"], ev["payload"])
        await asyncio.sleep(REPLAY_GAP_S)
    src = store.get("runs", source_id) or {}
    run = store.get("runs", run_id)
    run.update({"status": "finished", "finished_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "summary": src.get("summary", {}),
                **{k: src[k] for k in ("agent_id", "query") if k in src}})
    store.set("runs", run_id, run)
    registry.finish(run_id)


def create_app(store: Store, llm: LLM, registry: RunRegistry, replay: bool) -> FastAPI:
    app = FastAPI(title="MACS")
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
        return store.get("merchant_rules", "current")

    @app.put("/api/config/rules")
    async def put_rules(rules: MerchantRules):
        store.set("merchant_rules", "current", rules.model_dump())
        return rules

    @app.get("/api/agents")
    async def list_agents():
        return AGENTS

    @app.post("/api/runs")
    async def start_run(body: StartRun):
        if body.scenario is None:
            if not body.agent_id or not (body.query or "").strip():
                raise HTTPException(400, "provide either scenario, or agent_id and query")
            if body.agent_id not in AGENT_BY_ID:
                raise HTTPException(400, f"unknown agent_id {body.agent_id}")
            run_id = new_run_id()
            registry.open(run_id)
            _spawn(run_scenario("custom", run_id, store, llm, registry,
                                input=build_input(body.agent_id, body.query.strip())))
            return {"run_id": run_id}
        run_id = new_run_id()
        registry.open(run_id)
        if body.scenario in SCENARIOS and not replay:
            _spawn(run_scenario(body.scenario, run_id, store, llm, registry))
            return {"run_id": run_id}
        source = body.scenario
        if source in SCENARIOS:
            golden = [r for r in store.list_runs() if r.get("is_golden") and r.get("scenario") == source]
            if not golden:
                raise HTTPException(400, f"no golden run recorded for scenario {source}")
            source = golden[0]["run_id"]
        src = store.get("runs", source)
        if src is None:
            raise HTTPException(400, f"unknown scenario or run id {body.scenario}")
        _spawn(_replay_run(source, run_id, store, registry, src.get("scenario", "replay")))
        return {"run_id": run_id}

    @app.get("/api/runs")
    async def list_runs():
        runs = store.list_runs()
        golden = [r for r in runs if r.get("is_golden")]
        others = sorted((r for r in runs if not r.get("is_golden")), key=lambda r: r.get("started_at") or "", reverse=True)
        return golden + others

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        if store.get("runs", run_id) is None:
            raise HTTPException(404, "run not found")
        return store.list_events(run_id)

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(run_id: str):
        if not registry.has(run_id):
            if store.get("runs", run_id) is None:
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
    return create_app(_store_from_env(), LLM.from_env(), RunRegistry(), replay=os.environ.get("REPLAY") == "1")


app = build_from_env()
