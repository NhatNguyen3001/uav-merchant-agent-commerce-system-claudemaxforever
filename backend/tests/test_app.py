import json

import httpx
import pytest

from macs.app import create_app
from macs.emitter import RunRegistry
from macs.llm import LLM


@pytest.fixture
def app(seeded_store):
    return create_app(seeded_store, LLM(fake=True), RunRegistry(), replay=False)


async def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _drain_sse(client, run_id):
    events = []
    async with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


async def test_health_and_rules(app):
    async with await _client(app) as c:
        assert (await c.get("/health")).json()["status"] == "ok"
        rules = (await c.get("/api/config/rules")).json()
        assert rules["hard"]["max_discount_pct"] == 15
        rules["hard"]["max_discount_pct"] = 10
        assert (await c.put("/api/config/rules", json=rules)).status_code == 200
        assert (await c.get("/api/config/rules")).json()["hard"]["max_discount_pct"] == 10
        assert (await c.put("/api/config/rules", json={"soft": {}})).status_code == 422


async def test_start_run_and_stream_events(app):
    async with await _client(app) as c:
        r = await c.post("/api/runs", json={"scenario": "happy_path"})
        run_id = r.json()["run_id"]
        events = await _drain_sse(c, run_id)
        assert events[0]["id"] == 1
        assert events[-1]["payload"]["stage"] == "retailer_systems"
        runs = (await c.get("/api/runs")).json()
        assert runs[0]["run_id"] == run_id and runs[0]["status"] == "finished"
        full = (await c.get(f"/api/runs/{run_id}")).json()
        assert len(full) == len(events)


async def test_replay_of_finished_run_streams_from_store(app):
    async with await _client(app) as c:
        run_id = (await c.post("/api/runs", json={"scenario": "rejected_agent"})).json()["run_id"]
        first = await _drain_sse(c, run_id)
        replay_id = (await c.post("/api/runs", json={"scenario": run_id})).json()["run_id"]
        assert replay_id != run_id
        second = await _drain_sse(c, replay_id)
        assert [e["type"] for e in second] == [e["type"] for e in first]
        assert all(e["run_id"] == replay_id for e in second)


async def test_replay_of_custom_run_keeps_query_in_history(app):
    async with await _client(app) as c:
        run_id = (await c.post("/api/runs", json={"agent_id": "buyer-999", "query": "typed text"})).json()["run_id"]
        await _drain_sse(c, run_id)
        replay_id = (await c.post("/api/runs", json={"scenario": run_id})).json()["run_id"]
        await _drain_sse(c, replay_id)
        runs = {r["run_id"]: r for r in (await c.get("/api/runs")).json()}
        assert runs[replay_id]["query"] == "typed text" and runs[replay_id]["agent_id"] == "buyer-999"


async def test_unknown_scenario_is_400(app):
    async with await _client(app) as c:
        assert (await c.post("/api/runs", json={"scenario": "nope"})).status_code == 400
        assert (await c.post("/api/runs", json={})).status_code == 400
        assert (await c.post("/api/runs", json={"agent_id": "buyer-042", "query": "hi"})).status_code == 400


async def test_agents_endpoint_lists_identities(app):
    async with await _client(app) as c:
        agents = (await c.get("/api/agents")).json()
        assert [a["agent_id"] for a in agents] == ["buyer-001", "buyer-002", "buyer-999"]
        assert all({"agent_id", "label", "mandate_id"} <= set(a) for a in agents)


async def test_custom_query_runs_pipeline_with_typed_text(app):
    async with await _client(app) as c:
        r = await c.post("/api/runs", json={"agent_id": "buyer-001", "query": "Need a quiet mic setup for a tiny flat, budget 500"})
        run_id = r.json()["run_id"]
        events = await _drain_sse(c, run_id)
        first_msg = next(e for e in events if e["type"] == "message")
        assert first_msg["payload"]["text"] == "Need a quiet mic setup for a tiny flat, budget 500"
        assert events[-1]["payload"]["stage"] == "retailer_systems"
        run = (await c.get("/api/runs")).json()[0]
        assert run["scenario"] == "custom" and run["query"].startswith("Need a quiet") and run["agent_id"] == "buyer-001"


async def test_custom_query_with_unregistered_agent_blocks(app):
    async with await _client(app) as c:
        run_id = (await c.post("/api/runs", json={"agent_id": "buyer-999", "query": "anything"})).json()["run_id"]
        events = await _drain_sse(c, run_id)
        assert events[-1]["payload"] == {"stage": "inbound_gate", "status": "blocked",
                                         "note": "no credential on file for agent buyer-999"}


async def test_delete_run_and_clear_history_keep_golden(app, seeded_store):
    seeded_store.set("runs", "golden_x", {"run_id": "golden_x", "scenario": "happy_path", "is_golden": True,
                                          "started_at": "2026-09-12T10:00:00+10:00", "status": "finished", "summary": {}})
    async with await _client(app) as c:
        r1 = (await c.post("/api/runs", json={"scenario": "rejected_agent"})).json()["run_id"]
        await _drain_sse(c, r1)
        r2 = (await c.post("/api/runs", json={"scenario": "rejected_agent"})).json()["run_id"]
        await _drain_sse(c, r2)
        assert (await c.delete(f"/api/runs/{r1}")).json() == {"deleted": r1}
        assert (await c.get(f"/api/runs/{r1}")).status_code == 404
        assert (await c.delete("/api/runs/golden_x")).status_code == 403
        assert (await c.delete("/api/runs/nope")).status_code == 404
        assert (await c.delete("/api/runs")).json() == {"deleted": 1}
        ids = [r["run_id"] for r in (await c.get("/api/runs")).json()]
        assert ids == ["golden_x"]
