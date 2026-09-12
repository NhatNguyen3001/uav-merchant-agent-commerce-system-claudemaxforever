import asyncio

from macs.emitter import Emitter, RunRegistry
from macs.store import MemoryStore


def _make():
    store = MemoryStore()
    reg = RunRegistry()
    reg.open("r1")
    return store, reg, Emitter("r1", store, reg)


def test_ids_increment_and_events_go_to_store_and_registry():
    store, reg, em = _make()
    e1 = em.stage("protocol_adapter", "running")
    e2 = em.message("buyer_agent", "hello")
    assert (e1["id"], e2["id"]) == (1, 2)
    assert e1["lane"] == "system" and e2["lane"] == "a2a"
    assert e1["ts"].endswith("+10:00")
    assert [e["id"] for e in store.list_events("r1")] == [1, 2]
    assert [e["id"] for e in reg.events("r1")] == [1, 2]


def test_gate_emits_gate_then_paired_stage():
    store, reg, em = _make()
    em.gate("outbound", "corrected", "22% exceeds 15%", before={"discount_pct": 22}, after={"discount_pct": 15})
    evs = reg.events("r1")
    assert [e["type"] for e in evs] == ["gate", "stage"]
    assert evs[0]["payload"]["verdict"] == "corrected"
    assert evs[1]["payload"] == {"stage": "outbound_gate", "status": "passed", "note": "22% exceeds 15%"}


def test_blocked_gate_pairs_with_blocked_stage():
    store, reg, em = _make()
    em.gate("inbound", "blocked", "unknown agent")
    assert reg.events("r1")[1]["payload"]["status"] == "blocked"


async def test_wait_wakes_on_publish_and_finish_marks_done():
    store, reg, em = _make()

    async def later():
        await asyncio.sleep(0.01)
        em.stage("inbound_gate", "running")
        reg.finish("r1")

    task = asyncio.create_task(later())
    await reg.wait("r1")
    await task
    assert reg.is_done("r1")
    assert len(reg.events("r1")) == 1
