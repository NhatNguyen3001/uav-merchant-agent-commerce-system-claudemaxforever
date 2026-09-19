import json

import httpx
import pytest

from macs.app import create_app
from macs.emitter import RunRegistry
from macs.llm import LLM


JUDGE_A = "a" * 32
JUDGE_B = "b" * 32


@pytest.fixture
def app(seeded_store):
    return create_app(seeded_store, LLM(fake=True), RunRegistry(), replay=False)


async def _client(app, session: str | None = JUDGE_A):
    headers = {"X-MACS-Session": session} if session else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers)


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
        assert rules["hard"]["max_discount_pct"] == 15 and rules["locked"] is False
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


async def test_replay_does_not_add_to_history(app):
    async with await _client(app) as c:
        run_id = (await c.post("/api/runs", json={"agent_id": "buyer-999", "query": "typed text"})).json()["run_id"]
        await _drain_sse(c, run_id)
        before = [r["run_id"] for r in (await c.get("/api/runs")).json()]
        res = (await c.post("/api/runs", json={"scenario": run_id})).json()
        events = await _drain_sse(c, res["run_id"])
        assert res["replay_of"] == run_id and len(events) > 0
        after = [r["run_id"] for r in (await c.get("/api/runs")).json()]
        assert after == before
        assert (await c.get(f"/api/runs/{res['run_id']}")).status_code == 404


async def test_stale_running_runs_are_marked_interrupted_on_startup(seeded_store):
    seeded_store.set("runs", "r_stale", {"run_id": "r_stale", "scenario": "custom", "status": "running",
                                         "started_at": "2026-09-12T10:00:00+10:00", "is_golden": False, "summary": {}})
    create_app(seeded_store, LLM(fake=True), RunRegistry(), replay=False)
    run = seeded_store.get("runs", "r_stale")
    assert run["status"] == "interrupted" and run["summary"]["order_status"] == "none"


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
                                         "note": "No credential on file for agent buyer-999. Unregistered agents are refused."}


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


def _golden(store):
    store.set("runs", "golden_x", {"run_id": "golden_x", "scenario": "rejected_agent", "is_golden": True,
                                   "started_at": "2026-09-12T10:00:00+10:00", "status": "finished", "summary": {}})
    store.add_event("golden_x", {"id": 1, "run_id": "golden_x", "ts": "2026-09-12T10:00:00+10:00", "lane": "a2a",
                                 "type": "message", "payload": {"from": "buyer_agent", "text": "example"}})


async def test_locked_rules_cannot_be_changed(seeded_store):
    app = create_app(seeded_store, LLM(fake=True), RunRegistry(), replay=False, rules_locked=True)
    async with await _client(app) as c:
        rules = (await c.get("/api/config/rules")).json()
        assert rules["locked"] is True
        rules["hard"]["max_discount_pct"] = 60
        r = await c.put("/api/config/rules", json=rules)
        assert r.status_code == 403 and "locked" in r.json()["detail"].lower()
        assert (await c.get("/api/config/rules")).json()["hard"]["max_discount_pct"] == 15


async def test_starting_a_run_needs_a_valid_session(app):
    async with await _client(app, session=None) as c:
        assert (await c.post("/api/runs", json={"agent_id": "buyer-999", "query": "hi"})).status_code == 400
        assert (await c.get("/api/runs")).json() == []  # no session: no private runs, and no examples seeded here
    async with await _client(app, session="short") as c:
        assert (await c.post("/api/runs", json={"agent_id": "buyer-999", "query": "hi"})).status_code == 400


async def test_judges_only_see_and_touch_their_own_runs(app, seeded_store):
    _golden(seeded_store)
    async with await _client(app, JUDGE_A) as a, await _client(app, JUDGE_B) as b:
        rid = (await a.post("/api/runs", json={"agent_id": "buyer-999", "query": "my private note"})).json()["run_id"]
        await _drain_sse(a, rid)
        assert [r["run_id"] for r in (await a.get("/api/runs")).json()] == ["golden_x", rid]
        assert [r["run_id"] for r in (await b.get("/api/runs")).json()] == ["golden_x"]
        # judge B cannot open, stream, replay or delete judge A's run; not-found hides that it exists
        assert (await b.get(f"/api/runs/{rid}")).status_code == 404
        assert (await b.get(f"/api/runs/{rid}/events")).status_code == 404
        assert (await b.post("/api/runs", json={"scenario": rid})).status_code == 400
        assert (await b.delete(f"/api/runs/{rid}")).status_code == 404
        assert (await b.delete("/api/runs")).json() == {"deleted": 0}
        assert (await a.get(f"/api/runs/{rid}")).status_code == 200
        # the examples stay open to everyone
        assert (await b.get("/api/runs/golden_x")).status_code == 200
        replay = (await b.post("/api/runs", json={"scenario": "golden_x"})).json()
        assert replay["replay_of"] == "golden_x" and len(await _drain_sse(b, replay["run_id"])) == 1
        assert (await a.get(f"/api/runs/{replay['run_id']}/events")).status_code == 404
        assert (await a.delete("/api/runs")).json() == {"deleted": 1}


async def test_live_stream_is_private_and_accepts_the_key_in_the_url(app):
    async with await _client(app, JUDGE_A) as a, await _client(app, session=None) as anon:
        rid = (await a.post("/api/runs", json={"scenario": "rejected_agent"})).json()["run_id"]
        # the browser's EventSource cannot send headers, so the key rides in the query string
        assert (await anon.get(f"/api/runs/{rid}/events?session={JUDGE_B}")).status_code == 404
        events = []
        async with anon.stream("GET", f"/api/runs/{rid}/events?session={JUDGE_A}") as r:
            assert r.status_code == 200
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
        assert events and events[-1]["payload"]["status"] == "blocked"


async def test_runs_store_a_hash_of_the_session_not_the_key(app, seeded_store):
    import hashlib
    async with await _client(app, JUDGE_A) as a:
        rid = (await a.post("/api/runs", json={"agent_id": "buyer-999", "query": "x"})).json()["run_id"]
        await _drain_sse(a, rid)
    doc = seeded_store.get("runs", rid)
    assert doc["owner"] == hashlib.sha256(JUDGE_A.encode()).hexdigest() and JUDGE_A not in json.dumps(doc)
