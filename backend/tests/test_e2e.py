from macs.emitter import RunRegistry
from macs.graph.build import new_run_id, run_scenario
from macs.llm import LLM


async def test_happy_path_end_to_end(seeded_store):
    reg = RunRegistry()
    run_id = new_run_id()
    result = await run_scenario("happy_path", run_id, seeded_store, LLM(fake=True), reg)
    evs = reg.events(run_id)
    assert [e["id"] for e in evs] == list(range(1, len(evs) + 1))
    assert reg.is_done(run_id)
    gates = [e["payload"]["verdict"] for e in evs if e["type"] == "gate"]
    assert gates == ["pass", "corrected", "pass", "pass"]
    assert [e["payload"]["gate"] for e in evs if e["type"] == "gate"] == ["inbound", "outbound", "outbound", "execution"]
    assert sum(1 for e in evs if e["type"] == "proposal") == 3
    order = [e for e in evs if e["type"] == "order"][-1]["payload"]
    assert order["status"] == "placed" and order["total"] == 588
    assert evs[-1]["payload"] == {"stage": "retailer_systems", "status": "passed",
                                  "note": f"order {order['order_id']} placed, total 588"}
    for i, e in enumerate(evs):
        if e["type"] == "gate":
            assert evs[i + 1]["type"] == "stage"
    run = seeded_store.get("runs", run_id)
    assert run["status"] == "finished" and run["summary"]["order_status"] == "placed"
    assert seeded_store.list_events(run_id)[-1]["id"] == evs[-1]["id"]
    assert result["order"]["total"] == 588


async def test_rejected_agent_end_to_end(seeded_store):
    reg = RunRegistry()
    run_id = new_run_id()
    await run_scenario("rejected_agent", run_id, seeded_store, LLM(fake=True), reg)
    evs = reg.events(run_id)
    assert evs[-1]["payload"]["stage"] == "inbound_gate" and evs[-1]["payload"]["status"] == "blocked"
    assert not any(e["type"] == "intent" for e in evs)
    assert seeded_store.get("runs", run_id)["summary"]["order_status"] == "none"


async def test_failure_marks_run_failed(seeded_store, tmp_path):
    reg = RunRegistry()
    run_id = new_run_id()
    await run_scenario("happy_path", run_id, seeded_store, LLM(fake=True, fixtures_dir=tmp_path), reg)
    evs = reg.events(run_id)
    assert evs[-1]["payload"]["stage"] == "intent_decoder" and evs[-1]["payload"]["status"] == "blocked"
    assert seeded_store.get("runs", run_id)["status"] == "failed"
    assert reg.is_done(run_id)
