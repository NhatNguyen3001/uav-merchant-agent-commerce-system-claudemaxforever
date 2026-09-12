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


async def test_unknown_scenario_is_400(app):
    async with await _client(app) as c:
        assert (await c.post("/api/runs", json={"scenario": "nope"})).status_code == 400
