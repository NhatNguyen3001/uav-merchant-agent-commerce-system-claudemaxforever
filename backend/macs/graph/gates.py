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


def money(x: float) -> str:
    """US dollars for people: $179, $522.70, $1,650."""
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def _date(ts: str) -> str:
    return _parse(ts).strftime("%d %b %Y").lstrip("0")


def _scope_text(scope: str) -> str:
    return {"any": "any product category", "audio_equipment": "audio equipment only"}.get(scope, f"scope {scope}")


def _label(prod: dict) -> str:
    return f"{prod.get('name', prod['sku'])} ({prod['sku']})"


def check_inbound(store: Store, request: MerchantRequest, now: datetime) -> InboundResult:
    cred = store.get("credentials", request.agent_id)
    if cred is None:
        return InboundResult("blocked", f"No credential on file for agent {request.agent_id}. Unregistered agents are refused.")
    if cred.get("status") != "active":
        return InboundResult("blocked", f"The credential for {request.agent_id} is {cred.get('status')}.")
    mandate = store.get("mandates", request.mandate_id)
    if mandate is None or mandate.get("agent_id") != request.agent_id:
        return InboundResult("blocked", f"No mandate {request.mandate_id} on file for agent {request.agent_id}.", cred)
    if _parse(mandate["expires_at"]) <= now:
        return InboundResult("blocked", f"Mandate {request.mandate_id} expired on {_date(mandate['expires_at'])}.", cred, mandate)
    patterns = (store.get("injection_patterns", "current") or {}).get("phrases", [])
    text = " ".join([request.raw_query] + [m.content for m in request.conversation]).lower()
    for phrase in patterns:
        if phrase.lower() in text:
            return InboundResult("blocked", f"The message contains a blocked phrase: '{phrase}'.", cred, mandate)
    cap = mandate.get("spend_cap")
    cap_text = f"spend cap {money(cap)} {mandate['currency']}" if cap is not None else "no spend cap"
    return InboundResult("pass", f"{request.agent_id} is a registered agent. Mandate: {cap_text}, "
                                 f"{_scope_text(mandate['scope'])}, valid until {_date(mandate['expires_at'])}.", cred, mandate)


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
            return OutboundResult("blocked", f"{item.name} ({item.sku}) was not returned by any catalogue lookup in this run.", p)
    for item in p.items:
        prod = candidates[item.sku]
        if prod["ship_days"] > deliver_by_days:
            return OutboundResult("blocked", f"{_label(prod)} ships in {prod['ship_days']} days; the deadline is {deliver_by_days} days.", p)
        if prod["stock"] < 1:
            return OutboundResult("blocked", f"{_label(prod)} is out of stock.", p)
    slowest = max(candidates[i.sku]["ship_days"] for i in p.items) if p.items else 0
    if p.delivery_days != slowest:
        if p.delivery_days is not None:
            notes.append(f"delivery promise corrected from {p.delivery_days} to {slowest} days (slowest item)")
        p.delivery_days = slowest

    for item in p.items:
        prod = candidates[item.sku]
        if item.price != prod["list_price"]:
            notes.append(f"{_label(prod)} price {money(item.price)} corrected to the list price {money(prod['list_price'])}")
            item.price = prod["list_price"]
        certs = (prod.get("sustainability") or {}).get("certifications") or []
        if "values" in item.satisfies and not certs:
            notes.append(f"{_label(prod)} has no certification, so its sustainability claim was removed")
            item.satisfies = [s for s in item.satisfies if s != "values"]

    list_sum = sum(candidates[i.sku]["list_price"] for i in p.items)
    cost_sum = sum(candidates[i.sku]["cost"] for i in p.items)
    before = {"bundle_price": p.bundle_price, "discount_pct": p.discount_pct}
    cap_price = round(list_sum * (1 - hard.max_discount_pct / 100))
    if p.bundle_price < cap_price:
        actual = (1 - p.bundle_price / list_sum) * 100 if list_sum else 0
        notes.append(f"price {money(p.bundle_price)} is a {actual:.0f}% discount, above the merchant cap of "
                     f"{hard.max_discount_pct:g}%, so it was raised to {money(cap_price)}")
        p.bundle_price = cap_price
    floor_price = math.ceil(cost_sum / (1 - hard.min_margin_pct / 100))
    if p.bundle_price < floor_price:
        notes.append(f"price raised to {money(floor_price)} to keep the margin above {hard.min_margin_pct:g}%")
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
            notes.append(f"alternative referenced {', '.join(unknown)}, which no lookup returned, so it was removed")
            p.alternative = None
        else:
            alt_list = sum(candidates[s]["list_price"] for s in alt_skus)
            alt_cap = round(alt_list * (1 - hard.max_discount_pct / 100))
            if alt.bundle_price < alt_cap:
                notes.append(f"alternative price {money(alt.bundle_price)} corrected to {money(alt_cap)}")
                alt.bundle_price = alt_cap

    after = {"bundle_price": p.bundle_price, "discount_pct": p.discount_pct}
    delivery = f"Delivers in {slowest} day{'s' if slowest != 1 else ''} against a {deliver_by_days}-day deadline."
    if notes:
        return OutboundResult("corrected", "Corrected: " + "; ".join(notes) + f". {delivery}", p, before, after)
    return OutboundResult("pass", f"Bundle {money(p.bundle_price)} stays within the {hard.max_discount_pct:g}% discount cap and above "
                                  f"the margin floor. Every item came from a catalogue lookup. {delivery}", p)


def check_execution(proposal: Proposal, item_types: list[str], mandate: dict, now: datetime) -> ExecutionResult:
    if not mandate.get("signature"):
        return ExecutionResult("blocked", "The mandate signature is missing.")
    if _parse(mandate["expires_at"]) <= now:
        return ExecutionResult("blocked", f"The mandate expired on {_date(mandate['expires_at'])}.")
    scope = mandate.get("scope")
    if scope == "audio_equipment":
        if any(t not in AUDIO_TYPES for t in item_types):
            return ExecutionResult("blocked", f"The bundle includes items outside the mandate scope ({_scope_text(scope)}).")
    elif scope != "any":
        return ExecutionResult("blocked", f"Unsupported mandate scope {scope}.")
    cap = mandate.get("spend_cap")
    total = money(proposal.bundle_price)
    if cap is None:
        return ExecutionResult("pass", f"Total {total}. The mandate has no spend cap, and its scope and expiry are valid.")
    if proposal.bundle_price > cap:
        return ExecutionResult("blocked", f"Total {total} exceeds the mandate spend cap of {money(cap)}.")
    return ExecutionResult("pass", f"Total {total} is within the spend cap of {money(cap)}. Scope and expiry are valid.")
