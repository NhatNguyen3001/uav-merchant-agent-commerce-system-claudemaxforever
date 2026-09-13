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
                                  "note": "No credential on file for agent buyer-999. Unregistered agents are refused."}
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
    assert "Delivers in 2 days against a 7-day deadline." in gate["payload"]["reason"]
    search = [e for e in reg.events("r1") if e["type"] == "tool" and e["payload"]["name"] == "semantic_search"][0]
    assert "closest matches: " in search["payload"]["result_summary"] and "MIC-DYN-01" not in search["payload"]["result_summary"]
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
    assert closing["payload"]["text"] == f"Order placed: {state['order']['order_id']}, 4 items, total $588. Arrives within 2 days."
    assert state["order"]["ship_days"] == 2
    assert evs[-1]["payload"]["note"].endswith("ships in 2 days")
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


async def test_buyer_policy_overrides_model_action(seeded_store):
    from macs.graph.nodes import buyer_action
    assert (buyer_action("buyer-001", 1), buyer_action("buyer-001", 2)) == ("counter", "accept")
    assert (buyer_action("buyer-002", 1), buyer_action("buyer-002", 2)) == ("accept", "accept")
    # buyer-002 accepts the first proposal even though the round-1 fixture says counter
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent", "match_catalogue", "compose_proposal", "outbound_gate"):
        state.update(await nodes[name](state))
    state["request"]["agent_id"] = "buyer-002"
    state.update(await nodes["negotiate"](state))
    assert state["buyer_reply"]["action"] == "accept" and state["buyer_reply"]["counter_budget"] is None
    decision = [e for e in reg.events("r1") if e["type"] == "decision"][-1]["payload"]
    assert decision["action"] == "accept" and decision["round"] == 1
    await client.__aexit__(None, None, None)


async def test_match_catalogue_refuses_off_catalogue_request(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store, "custom")
    state["input"] = build_input(agent_id="buyer-002", query="Zorbing sphere rental for a birthday")
    for name in ("protocol_adapter", "inbound_gate"):
        state.update(await nodes[name](state))
    state["intent"] = Intent(goal="zorbing sphere rental", skill_level="any", environment=["outdoors"], values=[],
                             hard_constraints={"budget_max": 400, "deliver_by_days": 7}, soft_preferences=[]).model_dump()
    state.update(await nodes["match_catalogue"](state))
    assert state["blocked"] is True
    evs = reg.events("r1")
    gate = [e for e in evs if e["type"] == "gate"][-1]["payload"]
    assert gate["gate"] == "catalogue" and gate["verdict"] == "blocked" and gate["reason"].startswith("Nothing in the catalogue is close to")
    assert evs[-1]["payload"] == {"stage": "proposal_engine", "status": "blocked", "note": gate["reason"]}
    merchant = [e for e in evs if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"][-1]["payload"]["text"]
    assert merchant.startswith("Cannot proceed. We do not stock anything close to this request: 'zorbing sphere rental'.")
    assert state["gate_results"][-1] == {"gate": "catalogue", "verdict": "blocked"}
    await client.__aexit__(None, None, None)


async def test_match_catalogue_refuses_when_nothing_fits_the_limits(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent"):
        state.update(await nodes[name](state))
    state["intent"]["hard_constraints"]["budget_max"] = 5
    state.update(await nodes["match_catalogue"](state))
    assert state["blocked"] is True
    gate = [e for e in reg.events("r1") if e["type"] == "gate"][-1]["payload"]
    assert gate["gate"] == "catalogue" and "$5 budget and 7-day delivery" in gate["reason"]
    await client.__aexit__(None, None, None)


async def test_match_catalogue_passes_and_records_verdict(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent", "match_catalogue"):
        state.update(await nodes[name](state))
    assert state["blocked"] is False and state["gate_results"][-1] == {"gate": "catalogue", "verdict": "pass"}
    gate = [e for e in reg.events("r1") if e["type"] == "gate"][-1]["payload"]
    assert gate["gate"] == "catalogue" and gate["verdict"] == "pass" and "candidates within budget and delivery" in gate["reason"]
    await client.__aexit__(None, None, None)


async def test_compose_proposal_falls_back_cleanly_when_the_model_cannot_bundle(seeded_store):
    from macs.llm import LLMOutputError

    class Boom:
        async def structured(self, *a, **k):
            raise LLMOutputError("5 validation errors for Proposal\nitems\n  Field required")

    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent", "match_catalogue"):
        state.update(await nodes[name](state))
    failing = make_nodes(seeded_store, Boom(), tools, em, NOW)
    state.update(await failing["compose_proposal"](state))
    assert state["blocked"] is True
    evs = reg.events("r1")
    assert evs[-1]["payload"] == {"stage": "proposal_engine", "status": "blocked",
                                  "note": "Could not compose a bundle from the matching products."}
    merchant = [e for e in evs if e["type"] == "message" and e["payload"]["from"] == "merchant_agent"][-1]["payload"]["text"]
    assert merchant == "Cannot proceed. We could not compose a bundle from the matching products."
    assert not any(e["type"] == "proposal" for e in evs)
    await client.__aexit__(None, None, None)


async def test_compose_proposal_with_no_candidates_blocks_instead_of_raising(seeded_store):
    reg, em, client, tools, nodes, state = await _setup(seeded_store)
    for name in ("protocol_adapter", "inbound_gate", "decode_intent"):
        state.update(await nodes[name](state))
    state["candidates"] = {}
    state.update(await nodes["compose_proposal"](state))
    assert state["blocked"] is True
    assert reg.events("r1")[-1]["payload"] == {"stage": "proposal_engine", "status": "blocked",
                                               "note": "No matching products to build a bundle from."}
    await client.__aexit__(None, None, None)
