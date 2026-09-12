from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from macs.models import HardRules, MerchantRequest, Proposal
from macs.store import Store

AUDIO_TYPES = frozenset({"microphone", "audio_interface", "headphones", "boom_arm", "pop_filter",
                         "acoustic_panel", "cable", "kit"})


@dataclass
class InboundResult:
    verdict: str
    reason: str
    credential: dict | None = None
    mandate: dict | None = None


@dataclass
class OutboundResult:
    verdict: str
    reason: str
    proposal: Proposal
    before: dict | None = None
    after: dict | None = None


@dataclass
class ExecutionResult:
    verdict: str
    reason: str


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def check_inbound(store: Store, request: MerchantRequest, now: datetime) -> InboundResult:
    cred = store.get("credentials", request.agent_id)
    if cred is None:
        return InboundResult("blocked", f"no credential on file for agent {request.agent_id}")
    if cred.get("status") != "active":
        return InboundResult("blocked", f"credential for {request.agent_id} is {cred.get('status')}")
    mandate = store.get("mandates", request.mandate_id)
    if mandate is None or mandate.get("agent_id") != request.agent_id:
        return InboundResult("blocked", f"no mandate {request.mandate_id} for agent {request.agent_id}", cred)
    if _parse(mandate["expires_at"]) <= now:
        return InboundResult("blocked", f"mandate {request.mandate_id} expired at {mandate['expires_at']}", cred, mandate)
    patterns = (store.get("injection_patterns", "current") or {}).get("phrases", [])
    text = " ".join([request.raw_query] + [m.content for m in request.conversation]).lower()
    for phrase in patterns:
        if phrase.lower() in text:
            return InboundResult("blocked", f"injection pattern matched: '{phrase}'", cred, mandate)
    cap = mandate.get("spend_cap")
    cap_text = f"cap {cap:g} {mandate['currency']}" if cap is not None else "no spend cap"
    return InboundResult("pass", f"agent {request.agent_id} verified; mandate {cap_text}, "
                                 f"scope {mandate['scope']}, expires {mandate['expires_at']}", cred, mandate)


def check_outbound(proposal: Proposal, candidates: dict[str, dict], valid_ids: set[str],
                   hard: HardRules, deliver_by_days: int, shipping: dict[str, dict] | None = None) -> OutboundResult:
    """`shipping` maps sku -> {ship_days, stock} from get_shipping calls made for this proposal; when given it
    overrides the candidate records so the delivery promise is checked against fresh retailer data."""
    p = proposal.model_copy(deep=True)
    notes: list[str] = []
    if shipping:
        candidates = {sku: {**rec, **shipping.get(sku, {})} for sku, rec in candidates.items()}

    for item in p.items:
        if item.sku not in candidates or not item.grounded_on or any(
                ref.tool_result_id not in valid_ids or ref.sku != item.sku for ref in item.grounded_on):
            return OutboundResult("blocked", f"item {item.sku} is not grounded in a tool result of this run", p)
    for item in p.items:
        prod = candidates[item.sku]
        if prod["ship_days"] > deliver_by_days:
            return OutboundResult("blocked", f"item {item.sku} ships in {prod['ship_days']} days, deadline is {deliver_by_days}", p)
        if prod["stock"] < 1:
            return OutboundResult("blocked", f"item {item.sku} is out of stock", p)
    slowest = max(candidates[i.sku]["ship_days"] for i in p.items) if p.items else 0
    if p.delivery_days != slowest:
        if p.delivery_days is not None:
            notes.append(f"delivery promise {p.delivery_days} days corrected to {slowest} (slowest item)")
        p.delivery_days = slowest

    for item in p.items:
        prod = candidates[item.sku]
        if item.price != prod["list_price"]:
            notes.append(f"{item.sku} price {item.price:g} corrected to list {prod['list_price']:g}")
            item.price = prod["list_price"]
        certs = (prod.get("sustainability") or {}).get("certifications") or []
        if "values" in item.satisfies and not certs:
            notes.append(f"{item.sku} has no certification; sustainability claim removed")
            item.satisfies = [s for s in item.satisfies if s != "values"]

    list_sum = sum(candidates[i.sku]["list_price"] for i in p.items)
    cost_sum = sum(candidates[i.sku]["cost"] for i in p.items)
    before = {"bundle_price": p.bundle_price, "discount_pct": p.discount_pct}
    cap_price = round(list_sum * (1 - hard.max_discount_pct / 100))
    if p.bundle_price < cap_price:
        notes.append(f"bundle discount {p.discount_pct:g}% exceeds merchant cap of {hard.max_discount_pct:g}%")
        p.bundle_price = cap_price
    floor_price = math.ceil(cost_sum / (1 - hard.min_margin_pct / 100))
    if p.bundle_price < floor_price:
        notes.append(f"bundle margin below floor of {hard.min_margin_pct:g}%")
        p.bundle_price = floor_price
    p.discount_pct = round((1 - p.bundle_price / list_sum) * 100, 1) if list_sum else 0.0

    if p.alternative is not None:
        alt = p.alternative
        alt_skus = list(alt.items) if alt.items else None
        if alt_skus is None:
            # No item list given: assume the alternative swaps the one same-type item.
            alt_type = candidates.get(alt.sku, {}).get("type")
            alt_skus = [i.sku for i in p.items if candidates[i.sku]["type"] != alt_type] + [alt.sku]
        unknown = [s for s in alt_skus if s not in candidates]
        if unknown:
            notes.append(f"alternative references {', '.join(unknown)} outside this run's tool results; removed")
            p.alternative = None
        else:
            alt_list = sum(candidates[s]["list_price"] for s in alt_skus)
            alt_cap = round(alt_list * (1 - hard.max_discount_pct / 100))
            if alt.bundle_price < alt_cap:
                notes.append(f"alternative bundle {alt.bundle_price:g} corrected to {alt_cap:g}")
                alt.bundle_price = alt_cap

    after = {"bundle_price": p.bundle_price, "discount_pct": p.discount_pct}
    delivery = f"delivers in {slowest} day{'s' if slowest != 1 else ''} against a {deliver_by_days}-day deadline"
    if notes:
        return OutboundResult("corrected", "; ".join(notes) + f"; {delivery}", p, before, after)
    return OutboundResult("pass", f"bundle {p.bundle_price:g} within discount cap and margin floor; all items grounded; {delivery}", p)


def check_execution(proposal: Proposal, item_types: list[str], mandate: dict, now: datetime) -> ExecutionResult:
    if not mandate.get("signature"):
        return ExecutionResult("blocked", "mandate signature missing")
    if _parse(mandate["expires_at"]) <= now:
        return ExecutionResult("blocked", f"mandate expired at {mandate['expires_at']}")
    scope = mandate.get("scope")
    if scope == "audio_equipment":
        if any(t not in AUDIO_TYPES for t in item_types):
            return ExecutionResult("blocked", f"items outside mandate scope {scope}")
    elif scope != "any":
        return ExecutionResult("blocked", f"unsupported mandate scope {scope}")
    cap = mandate.get("spend_cap")
    if cap is None:
        return ExecutionResult("pass", f"total {proposal.bundle_price:g}; mandate has no spend cap; scope and expiry valid")
    if proposal.bundle_price > cap:
        return ExecutionResult("blocked", f"total {proposal.bundle_price:g} exceeds mandate cap {cap:g}")
    return ExecutionResult("pass", f"total {proposal.bundle_price:g} within cap {cap:g}; scope and expiry valid")
