from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Callable

from macs.emitter import Emitter
from macs.graph.gates import check_execution, check_inbound, check_outbound, money
from macs.graph.tools import ToolCaller
from macs.llm import LLM
from macs.models import BuyerDecision, HardRules, Intent, MerchantRequest, Proposal
from macs.scenarios import AGENT_BY_ID, SCENARIOS
from macs.store import Store

INTENT_SYSTEM = """You are the intent decoder for a retailer that sells to AI shopping agents.
Read the buyer agent's request and produce a structured Intent. Capture the goal, the buyer's
skill level, the physical environment, the values they care about, hard constraints (budget_max as a
number, deliver_by_days as an integer count of days), and soft preferences. Only include facts stated
or clearly implied by the request. If the request says nothing about a list field, return an empty list;
never write placeholders such as unknown or N/A."""

PROPOSAL_SYSTEM = """You are the merchant agent for a podcasting equipment retailer. Compose a product bundle
for the buyer agent from the candidate products only. Rules for this merchant:
{soft_rules}

Requirements:
- Choose 3 to 5 items that together satisfy the decoded intent. Use one item per type.
- Every item price must equal the candidate's list_price.
- Give one rationale per item, one sentence of at most 25 words, tying the item to specific intent
  facets, and list which intent keys it satisfies (goal, skill_level, environment, values,
  hard_constraints, soft_preferences).
  Claim 'values' only when the intent lists values AND the product's sustainability.certifications is non-empty.
- grounded_on must cite the tool_result_id given below for each item's sku.
- Budget first: choose items whose list prices add up to no more than the buyer's budget_max. Do not rely
  on a discount to get under budget.
- bundle_price is the total you propose after any bundle discount; discount_pct is the discount off the
  sum of list prices, so bundle_price = sum of list prices x (1 - discount_pct / 100). Keep any discount
  modest, single digits; the merchant's gates will reduce anything larger.
- Provide one cheaper alternative bundle. Set alternative.sku and name to the item that changed, list
  every SKU in the alternative under alternative.items, give its full bundle price, and state the tradeoff.
- intent_coverage is 'satisfied/total' constraints, for example '6/6'.
- expires_at is {expires_at}."""

BUYER_SYSTEM = """You are an autonomous shopping agent acting for a person under a spending mandate.
Mandate: {cap_text}, scope {scope}. Your principal's request: {query}
You will see the merchant's proposal. This is round {round} of at most 2.
{stance}
Keep message to two sentences."""

BUYER_STANCE = {
    "counter": ("Your stance this round: counter. Acknowledge what the bundle gets right, then ask for a modestly "
                "lower price (5 to 8 percent lower) and give counter_budget. If something in the request is missing, "
                "name it. Set action to counter."),
    "accept": ("Your stance this round: accept. Confirm that the bundle meets the request and the mandate and that "
               "the merchant may proceed. Set action to accept."),
}


def buyer_action(agent_id: str, rnd: int) -> str:
    """Deterministic per-agent negotiation policy; the model writes the words, this decides the action."""
    policy = AGENT_BY_ID.get(agent_id, {}).get("negotiation", "counter_then_accept")
    if policy == "accept_first":
        return "accept"
    return "counter" if rnd == 1 else "accept"


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
            em.message("merchant_agent", f"Cannot proceed. {r.reason}")
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
        drop = ("specs", "embedding", "compatibility", "tool_result_id", "title_full", "url", "image_url", "ratings", "source_category")
        slim = [{k: v for k, v in p.items() if k not in drop} for p in cands.values()]
        user = (f"Decoded intent:\n{json.dumps(state['intent'], indent=2)}\n\n"
                f"Candidate products (tool_result_id for every sku is {tid}):\n{json.dumps(slim, indent=2)}")
        if state.get("buyer_reply"):
            user += (f"\n\nYour previous proposal was {state['proposal']['bundle_price']}. The buyer agent replied: "
                     f"{state['buyer_reply']['message']}\nRespond with your final proposal.")
        proposal = await llm.structured(Proposal, system, user,
                                        fixture=f"record_proposal_{_fixture_scenario(state)}_{rnd}", tool_result_id=tid)
        known = [cands[i.sku]["ship_days"] for i in proposal.items if i.sku in cands]
        proposal.delivery_days = max(known) if known else None
        em.emit("a2a", "proposal", proposal.model_dump())
        deadline = state["intent"]["hard_constraints"]["deliver_by_days"]
        delivery = ""
        if proposal.delivery_days is not None:
            fit = "inside" if proposal.delivery_days <= deadline else "outside"
            delivery = (f" Delivered within {proposal.delivery_days} day{'s' if proposal.delivery_days != 1 else ''}, "
                        f"{fit} your {deadline}-day window.")
        if proposal.alternative:
            text = (f"Proposed {len(proposal.items)} items for {money(proposal.bundle_price)} "
                    f"({proposal.discount_pct:.0f}% bundle discount).{delivery} Alternative at {money(proposal.alternative.bundle_price)}.")
        else:
            text = f"Proposed {len(proposal.items)} items for {money(proposal.bundle_price)}.{delivery}"
        em.message("merchant_agent", text)
        em.stage("proposal_engine", "passed", f"{len(proposal.items)} items, coverage {proposal.intent_coverage}")
        return {"proposal": proposal.model_dump()}

    async def outbound_gate(state: dict) -> dict:
        em.stage("outbound_gate", "running")
        hard = HardRules.model_validate((store.get("merchant_rules", "current") or {})["hard"])
        proposal = Proposal.model_validate(state["proposal"])
        # Verify the delivery promise against fresh retailer data: one get_shipping call per proposed item.
        shipping: dict[str, dict] = {}
        for sku in dict.fromkeys(i.sku for i in proposal.items):
            if sku in state["candidates"]:
                data, _ = await tools.call("get_shipping", {"sku": sku})
                shipping[sku] = {"ship_days": data["ship_days"], "stock": data["stock"]}
        r = check_outbound(proposal, state["candidates"], tools.issued, hard,
                           state["intent"]["hard_constraints"]["deliver_by_days"], shipping)
        if r.verdict == "blocked":
            em.message("merchant_agent", f"Cannot proceed. {r.reason}")
        em.gate("outbound", r.verdict, r.reason, r.before, r.after)
        if r.verdict == "corrected":
            em.emit("a2a", "proposal", r.proposal.model_dump())
        return {"proposal": r.proposal.model_dump(), "blocked": r.verdict == "blocked",
                "gate_results": state["gate_results"] + [{"gate": "outbound", "verdict": r.verdict}]}

    async def negotiate(state: dict) -> dict:
        rnd = state["negotiation_round"] + 1
        m = state["mandate"]
        cap_text = f"cap {m['spend_cap']:g} {m['currency']}" if m.get("spend_cap") is not None else "no spend cap"
        action = buyer_action(state["request"]["agent_id"], rnd)
        system = BUYER_SYSTEM.format(cap_text=cap_text, scope=m["scope"], query=state["request"]["raw_query"],
                                     round=rnd, stance=BUYER_STANCE[action])
        user = "Merchant proposal:\n" + json.dumps(state["proposal"], indent=2)
        decision = await llm.structured(BuyerDecision, system, user, fixture=f"buyer_decision_{_fixture_scenario(state)}_{rnd}")
        decision.action = action  # the policy decides; the model only wrote the reply
        if action == "accept":
            decision.counter_budget = None
        em.message("buyer_agent", decision.message)
        em.emit("a2a", "decision", {"round": rnd, "action": decision.action, "message": decision.message,
                                    "counter_budget": decision.counter_budget,
                                    "proposal_price": state["proposal"]["bundle_price"]})
        return {"negotiation_round": rnd, "buyer_reply": decision.model_dump(), "counter_budget": decision.counter_budget}

    async def execution_gate(state: dict) -> dict:
        em.stage("execution_gate", "running")
        proposal = Proposal.model_validate(state["proposal"])
        skus = [i.sku for i in proposal.items]
        reply = state.get("buyer_reply") or {}
        if reply.get("action") != "accept":
            # Two rounds are up and the buyer's agent has not accepted: nothing is ordered.
            reason = "The buyer's agent did not accept the final proposal, so no order was placed."
            em.message("merchant_agent", "No order placed. We could not reach agreement within two rounds; "
                                         "the final proposal stays open until it expires.")
            em.gate("execution", "blocked", reason)
            order = {"order_id": "", "skus": skus, "total": proposal.bundle_price,
                     "mandate_id": state["mandate"]["mandate_id"], "status": "rejected", "ship_days": None}
            em.emit("a2a", "order", order)
            return {"order": order, "blocked": True,
                    "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "blocked"}]}
        types = [state["candidates"][i.sku]["type"] for i in proposal.items]
        r = check_execution(proposal, types, state["mandate"], now)
        if r.verdict == "blocked":
            em.message("merchant_agent", f"Cannot proceed. {r.reason}")
        em.gate("execution", r.verdict, r.reason)
        if r.verdict == "blocked":
            order = {"order_id": "", "skus": skus, "total": proposal.bundle_price,
                     "mandate_id": state["mandate"]["mandate_id"], "status": "rejected", "ship_days": None}
            em.emit("a2a", "order", order)
            return {"order": order, "blocked": True,
                    "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "blocked"}]}
        em.stage("retailer_systems", "running")
        data, _ = await tools.call("create_order", {"skus": skus, "mandate_id": state["mandate"]["mandate_id"],
                                                    "total": proposal.bundle_price})
        order = {**data, "total": proposal.bundle_price}
        em.emit("a2a", "order", order)
        days = order.get("ship_days")
        arrival = f" Arrives within {days} day{'s' if days != 1 else ''}." if days is not None else ""
        em.message("merchant_agent", f"Order placed: {order['order_id']}, {len(skus)} items, total {money(order['total'])}.{arrival}")
        em.stage("retailer_systems", "passed", f"order {order['order_id']} placed, total {order['total']:g}"
                                               + (f", ships in {days} day{'s' if days != 1 else ''}" if days is not None else ""))
        return {"order": order, "gate_results": state["gate_results"] + [{"gate": "execution", "verdict": "pass"}]}

    return {
        "protocol_adapter": protocol_adapter, "inbound_gate": inbound_gate, "decode_intent": decode_intent,
        "match_catalogue": match_catalogue, "compose_proposal": compose_proposal, "outbound_gate": outbound_gate,
        "negotiate": negotiate, "execution_gate": execution_gate,
    }
