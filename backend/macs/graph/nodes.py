from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Callable

from macs.emitter import Emitter
from macs.graph.gates import check_execution, check_inbound, check_outbound
from macs.graph.tools import ToolCaller
from macs.llm import LLM
from macs.models import BuyerDecision, HardRules, Intent, MerchantRequest, Proposal
from macs.scenarios import SCENARIOS
from macs.store import Store

INTENT_SYSTEM = """You are the intent decoder for a retailer that sells to AI shopping agents.
Read the buyer agent's request and produce a structured Intent. Capture the goal, the buyer's
skill level, the physical environment, the values they care about, hard constraints (budget_max as a
number, deliver_by_days as an integer count of days), and soft preferences. Only include facts stated
or clearly implied by the request."""

PROPOSAL_SYSTEM = """You are the merchant agent for a podcasting equipment retailer. Compose a product bundle
for the buyer agent from the candidate products only. Rules for this merchant:
{soft_rules}

Requirements:
- Choose 3 to 5 items that together satisfy the decoded intent. Use one item per type.
- Every item price must equal the candidate's list_price.
- Give one rationale per item that ties the item to specific intent facets, and list which intent
  keys it satisfies (goal, skill_level, environment, values, hard_constraints, soft_preferences).
  Only claim 'values' for products whose sustainability.certifications is non-empty.
- grounded_on must cite the tool_result_id given below for each item's sku.
- bundle_price is the total you propose after any bundle discount; discount_pct is the discount off
  the sum of list prices. A modest discount can help close, but the bundle must stay within the buyer's budget.
- Provide one cheaper alternative that swaps a single item for a lower-priced candidate of the same
  type, with its full bundle price and the tradeoff.
- intent_coverage is 'satisfied/total' constraints, for example '6/6'.
- expires_at is {expires_at}."""

BUYER_SYSTEM = """You are an autonomous shopping agent acting for a person under a spending mandate.
Mandate: {cap_text}, scope {scope}. Your principal's request: {query}
You will see the merchant's proposal. Round {round} of at most 2.
Round 1: if the bundle is acceptable, counter once asking for a modestly lower price (5 to 8 percent
lower) and give counter_budget. Round 2: accept if within the mandate, otherwise counter with the alternative.
Keep message to two sentences."""


def _fixture_scenario(state: dict) -> str:
    return state["scenario"] if state["scenario"] in SCENARIOS else "happy_path"


def intent_query(intent: Intent) -> str:
    return (f"{intent.goal} for a {intent.skill_level}; environment: {', '.join(intent.environment)}; "
            f"values: {', '.join(intent.values)}; preferences: {', '.join(intent.soft_preferences)}")


def make_nodes(store: Store, llm: LLM, tools: ToolCaller, em: Emitter, now: datetime) -> dict[str, Callable]:

    async def protocol_adapter(state: dict) -> dict:
        em.stage("protocol_adapter", "running")
        raw = state.get("input") or SCENARIOS[state["scenario"]]
        req = MerchantRequest(
            request_id="req_" + uuid.uuid4().hex[:8], protocol=raw["protocol"], agent_id=raw["agent_id"],
            mandate_id=raw["mandate_id"], raw_query=raw["messages"][-1]["content"],
            conversation=[{"role": m["role"], "content": m["content"]} for m in raw["messages"][:-1]],
        )
        em.message("buyer_agent", req.raw_query)
        em.stage("protocol_adapter", "passed", f"{req.protocol.upper()} message mapped to MerchantRequest")
        return {"request": req.model_dump()}

    async def inbound_gate(state: dict) -> dict:
        em.stage("inbound_gate", "running")
        req = MerchantRequest.model_validate(state["request"])
        r = check_inbound(store, req, now)
        if r.verdict == "blocked":
            em.message("merchant_agent", f"Cannot proceed: {r.reason}.")
        em.gate("inbound", r.verdict, r.reason)
        return {"credential": r.credential, "mandate": r.mandate, "blocked": r.verdict == "blocked",
                "gate_results": state["gate_results"] + [{"gate": "inbound", "verdict": r.verdict}]}

    async def decode_intent(state: dict) -> dict:
        em.stage("intent_decoder", "running")
        intent = await llm.structured(Intent, INTENT_SYSTEM, state["request"]["raw_query"],
                                      fixture=f"record_intent_{_fixture_scenario(state)}")
        em.emit("a2a", "intent", intent.model_dump())
        em.stage("intent_decoder", "passed", f"{intent.constraint_count} constraints decoded")
        return {"intent": intent.model_dump()}

    async def match_catalogue(state: dict) -> dict:
        em.stage("proposal_engine", "running")
        intent = Intent.model_validate(state["intent"])
        hits, _ = await tools.call("semantic_search", {"query_text": intent_query(intent), "k": 15})
        skus = [h["sku"] for h in hits]
        products, tid = await tools.call("search_products", {
            "sku_in": skus, "max_price": intent.hard_constraints.budget_max,
            "max_ship_days": intent.hard_constraints.deliver_by_days,
        })
        candidates = {p["sku"]: {**p, "tool_result_id": tid} for p in products}
        return {"candidates": candidates}

    async def compose_proposal(state: dict) -> dict:
        rnd = state["negotiation_round"] + 1
        if rnd > 1:
            em.stage("proposal_engine", "running", f"negotiation round {rnd}")
        soft = (store.get("merchant_rules", "current") or {})["soft"]
        cands = state["candidates"]
        tid = next(iter(cands.values()))["tool_result_id"]
        expires = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        system = PROPOSAL_SYSTEM.format(soft_rules=json.dumps(soft, indent=2), expires_at=expires)
        slim = [{k: v for k, v in p.items() if k not in ("specs", "embedding")} for p in cands.values()]
        user = (f"Decoded intent:\n{json.dumps(state['intent'], indent=2)}\n\n"
                f"Candidate products (tool_result_id for every sku is {tid}):\n{json.dumps(slim, indent=2)}")
        if state.get("buyer_reply"):
            user += (f"\n\nYour previous proposal was {state['proposal']['bundle_price']}. The buyer agent replied: "
                     f"{state['buyer_reply']['message']}\nRespond with your final proposal.")
        proposal = await llm.structured(Proposal, system, user,
                                        fixture=f"record_proposal_{_fixture_scenario(state)}_{rnd}", tool_result_id=tid)
        em.emit("a2a", "proposal", proposal.model_dump())
        if proposal.alternative:
            text = (f"Proposed {len(proposal.items)} items at {proposal.bundle_price:g} "
                    f"({proposal.discount_pct:g}% bundle discount). Alternative at {proposal.alternative.bundle_price:g}.")
        else:
            text = f"Proposed {len(proposal.items)} items at {proposal.bundle_price:g}."
        em.message("merchant_agent", text)
        em.stage("proposal_engine", "passed", f"{len(proposal.items)} items, coverage {proposal.intent_coverage}")
        return {"proposal": proposal.model_dump()}

    async def outbound_gate(state: dict) -> dict:
        em.stage("outbound_gate", "running")
        hard = HardRules.model_validate((store.get("merchant_rules", "current") or {})["hard"])
        proposal = Proposal.model_validate(state["proposal"])
        r = check_outbound(proposal, state["candidates"], tools.issued, hard,
                           state["intent"]["hard_constraints"]["deliver_by_days"])
        if r.verdict == "blocked":
            em.message("merchant_agent", f"Cannot proceed: {r.reason}.")
        em.gate("outbound", r.verdict, r.reason, r.before, r.after)
        if r.verdict == "corrected":
            em.emit("a2a", "proposal", r.proposal.model_dump())
        return {"proposal": r.proposal.model_dump(), "blocked": r.verdict == "blocked",
                "gate_results": state["gate_results"] + [{"gate": "outbound", "verdict": r.verdict}]}

    async def negotiate(state: dict) -> dict:
        rnd = state["negotiation_round"] + 1
        m = state["mandate"]
        cap_text = f"cap {m['spend_cap']:g} {m['currency']}" if m.get("spend_cap") is not None else "no spend cap"
        system = BUYER_SYSTEM.format(cap_text=cap_text, scope=m["scope"], query=state["request"]["raw_query"], round=rnd)
        user = "Merchant proposal:\n" + json.dumps(state["proposal"], indent=2)
        decision = await llm.structured(BuyerDecision, system, user, fixture=f"buyer_decision_{_fixture_scenario(state)}_{rnd}")
        em.message("buyer_agent", decision.message)
        return {"negotiation_round": rnd, "buyer_reply": decision.model_dump(), "counter_budget": decision.counter_budget}

    async def execution_gate(state: dict) -> dict:
        em.stage("execution_gate", "running")
        proposal = Proposal.model_validate(state["proposal"])
        skus = [i.sku for i in proposal.items]
        reply = state.get("buyer_reply") or {}
        if reply.get("action") != "accept":
            # Two rounds are up and the buyer's agent has not accepted: nothing is ordered.
            reason = "buyer's agent did not accept the final proposal; no order placed"
            em.message("merchant_agent", "No order placed. We could not reach agreement within two rounds; "
                                         "the final proposal stays open until it expires.")
            em.gate("execution", "blocked", reason)
            order = {"order_id": "", "skus": skus, "total": proposal.bundle_price,
                     "mandate_id": state["mandate"]["mandate_id"], "status": "rejected"}
            em.emit("a2a", "order", order)
            return {"order": order, "blocked": True,
                    "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "blocked"}]}
        types = [state["candidates"][i.sku]["type"] for i in proposal.items]
        r = check_execution(proposal, types, state["mandate"], now)
        if r.verdict == "blocked":
            em.message("merchant_agent", f"Cannot proceed: {r.reason}.")
        em.gate("execution", r.verdict, r.reason)
        if r.verdict == "blocked":
            order = {"order_id": "", "skus": skus, "total": proposal.bundle_price,
                     "mandate_id": state["mandate"]["mandate_id"], "status": "rejected"}
            em.emit("a2a", "order", order)
            return {"order": order, "blocked": True,
                    "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "blocked"}]}
        em.stage("retailer_systems", "running")
        data, _ = await tools.call("create_order", {"skus": skus, "mandate_id": state["mandate"]["mandate_id"]})
        order = {**data, "total": proposal.bundle_price}
        em.emit("a2a", "order", order)
        em.message("merchant_agent", f"Order placed: {order['order_id']}, {len(skus)} items, total {order['total']:g}. "
                                     f"Confirmation goes to mandate {order['mandate_id']}.")
        em.stage("retailer_systems", "passed", f"order {order['order_id']} placed, total {order['total']:g}")
        return {"order": order, "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "pass"}]}

    return {
        "protocol_adapter": protocol_adapter, "inbound_gate": inbound_gate, "decode_intent": decode_intent,
        "match_catalogue": match_catalogue, "compose_proposal": compose_proposal, "outbound_gate": outbound_gate,
        "negotiate": negotiate, "execution_gate": execution_gate,
    }
