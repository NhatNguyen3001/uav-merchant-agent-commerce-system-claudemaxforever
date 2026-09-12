from datetime import datetime, timedelta, timezone

from fastmcp import Client

from macs.emitter import Emitter, RunRegistry
from macs.graph.nodes import intent_query, make_nodes
from macs.graph.tools import ToolCaller
from macs.llm import LLM
from macs.mcp_server import build_server
from macs.models import Intent
from macs.scenarios import SCENARIOS, build_input

TZ = timezone(timedelta(hours=10))
NOW = datetime(2026, 9, 12, 10, 0, tzinfo=TZ)


def test_intent_query_mentions_every_facet():
    intent = Intent(goal="record a podcast", skill_level="beginner", environment=["noisy street"],
                    values=["sustainable"], hard_constraints={"budget_max": 600, "deliver_by_days": 7},
                    soft_preferences=["simple setup"])
    q = intent_query(intent)
    for word in ("podcast", "beginner", "noisy", "sustainable", "simple"):
        assert word in q


async def _setup(seeded_store, scenario="happy_path"):
    reg = RunRegistry()
    reg.open("r1")
    em = Emitter("r1", seeded_store, reg)
    client = Client(build_server(seeded_store))
    await client.__aenter__()
    tools = ToolCaller(client, em)
    nodes = make_nodes(seeded_store, LLM(fake=True), tools, em, NOW)
    state = {"scenario": scenario, "gate_results": [], "negotiation_round": 0, "blocked": False, "candidates": {}}
    return reg, em, client, tools, nodes, state


async def test_adapter_and_inbound_pass(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    state.update(await nodes["protocol_adapter"](state))
    assert state["request"]["agent_id"] == "buyer-001"
    state.update(await nodes["inbound_gate"](state))
    assert state["blocked"] is False and state["mandate"]["spend_cap"] is None
    types = [e["type"] for e in reg.events("r1")]
    assert types == ["stage", "message", "stage", "stage", "gate", "stage"]
    await client.__aexit__(None, None, None)


async def test_adapter_uses_custom_input_when_present(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store, "custom")
    state["input"] = build_input(agent_id="buyer-002", query="Cheap lavalier for interviews")
    state.update(await nodes["protocol_adapter"](state))
    assert state["request"]["agent_id"] == "buyer-002" and state["request"]["mandate_id"] == "mandate-002"
    assert state["request"]["raw_query"] == "Cheap lavalier for interviews"
    assert reg.events("r1")[1]["payload"]["text"] == "Cheap lavalier for interviews"
    await client.__aexit__(None, None, None)


async def test_inbound_blocks_rejected_agent(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store, "rejected_agent")
    state.update(await nodes["protocol_adapter"](state))
    state.update(await nodes["inbound_gate"](state))
    assert state["blocked"] is True
    evs = reg.events("r1")
    assert evs[-1]["payload"] == {"stage": "inbound_gate", "status": "blocked",
                                  "note": "no credential on file for agent buyer-999"}
    merchant = [e for e in evs if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"]
    assert merchant and merchant[-1]["payload"]["text"].startswith("Cannot proceed")
    await client.__aexit__(None, None, None)


async def test_decode_match_compose_outbound_negotiate(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent", "match_catalogue", "compose_proposal", "outbound_gate"):
        state.update(await nodes[name](state))
    assert state["intent"]["constraint_count"] == 6
    assert {"MIC-DYN-01", "IF-USB-02", "HP-REC-01", "ARM-DESK-01", "IF-USB-01"} <= set(state["candidates"])
    assert state["proposal"]["bundle_price"] == 588 and state["proposal"]["discount_pct"] == 15
    assert state["proposal"]["delivery_days"] == 2
    gate = [e for e in reg.events("r1") if e["type"] == "gate" and e["payload"]["gate"] == "outbound"][0]
    assert gate["payload"]["verdict"] == "corrected" and gate["payload"]["after"]["bundle_price"] == 588
    assert "delivers in 2 days against a 7-day deadline" in gate["payload"]["reason"]
    shipping_calls = [e for e in reg.events("r1") if e["type"] == "tool" and e["payload"]["name"] == "get_shipping"]
    assert [c["payload"]["args"]["sku"] for c in shipping_calls] == ["MIC-DYN-01", "IF-USB-02", "HP-REC-01", "ARM-DESK-01"]
    merchant = [e for e in reg.events("r1") if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"][-1]
    assert "Delivered within 2 days, inside your 7-day window" in merchant["payload"]["text"]
    state.update(await nodes["negotiate"](state))
    assert state["negotiation_round"] == 1 and state["buyer_reply"]["action"] == "counter"
    decision = [e for e in reg.events("r1") if e["type"] == "decision"][-1]["payload"]
    assert decision == {"round": 1, "action": "counter", "message": state["buyer_reply"]["message"],
                        "counter_budget": 560, "proposal_price": 588}
    state.update(await nodes["compose_proposal"](state))
    state.update(await nodes["outbound_gate"](state))
    state.update(await nodes["negotiate"](state))
    assert state["negotiation_round"] == 2 and state["buyer_reply"]["action"] == "accept"
    state.update(await nodes["execution_gate"](state))
    assert state["order"]["status"] == "placed" and state["order"]["total"] == 588
    evs = reg.events("r1")
    assert evs[-1]["payload"]["stage"] == "retailer_systems"
    closing = [e for e in evs if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"][-1]
    assert closing["payload"]["text"].startswith("Order placed") and "588" in closing["payload"]["text"]
    await client.__aexit__(None, None, None)


async def test_execution_gate_refuses_to_order_without_buyer_acceptance(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent", "match_catalogue", "compose_proposal", "outbound_gate"):
        state.update(await nodes[name](state))
    state["negotiation_round"] = 2
    state["buyer_reply"] = {"action": "counter", "message": "Still not right.", "counter_budget": 500}
    state.update(await nodes["execution_gate"](state))
    assert state["order"]["status"] == "rejected" and state["blocked"] is True
    evs = reg.events("r1")
    gate = [e for e in evs if e["type"] == "gate" and e["payload"]["gate"] == "execution"][-1]["payload"]
    assert gate["verdict"] == "blocked" and "did not accept" in gate["reason"]
    assert not any(e["type"] == "tool" and e["payload"]["name"] == "create_order" for e in evs)
    closing = [e for e in evs if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"][-1]
    assert closing["payload"]["text"].startswith("No order")
    await client.__aexit__(None, None, None)
