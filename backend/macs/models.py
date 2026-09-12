from __future__ import annotations

from typing import Literal, Optional

import json
from typing import Any, get_args, get_origin

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

Lane = Literal["merchant", "a2a", "system"]
EventType = Literal["message", "tool", "gate", "stage", "intent", "proposal", "decision", "order"]
StageName = Literal[
    "protocol_adapter", "inbound_gate", "intent_decoder", "proposal_engine",
    "outbound_gate", "execution_gate", "retailer_systems",
]
StageStatus = Literal["idle", "running", "passed", "blocked"]
GateName = Literal["inbound", "outbound", "execution"]
Verdict = Literal["pass", "blocked", "corrected"]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class MerchantRequest(BaseModel):
    request_id: str
    protocol: Literal["acp", "ucp"]
    agent_id: str
    mandate_id: str
    raw_query: str
    conversation: list[Message] = Field(default_factory=list)


class HardConstraints(BaseModel):
    budget_max: float
    deliver_by_days: int


def _listify(v):
    """Models sometimes return a single string where a list is expected; wrap it instead of failing the run."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return v


def _wants_structure(annotation) -> bool:
    origin = get_origin(annotation)
    if origin in (list, dict):
        return True
    if origin is not None:  # Optional[X], Union[...]
        return any(_wants_structure(a) for a in get_args(annotation) if a is not type(None))
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


class LenientModel(BaseModel):
    """Tolerates the two common slips of unconstrained tool output: a JSON-encoded string where a list or
    object was expected, and a bare string where a list was expected."""

    @model_validator(mode="before")
    @classmethod
    def _decode_stringified(cls, data: Any):
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for name, field in cls.model_fields.items():
            v = out.get(name)
            if isinstance(v, str) and _wants_structure(field.annotation):
                text = v.strip()
                if text[:1] in "[{":
                    try:
                        out[name] = json.loads(text)
                        continue
                    except ValueError:
                        pass
                if get_origin(field.annotation) is list:
                    out[name] = _listify(v)
        return out


_PLACEHOLDER = {"unknown", "none", "n/a", "na", "not specified", "not stated", "null", "nil", ""}


def _drop_placeholders(items: list) -> list:
    out = []
    for x in items:
        text = str(x).strip().strip("<>[]()").strip().lower()
        if text not in _PLACEHOLDER:
            out.append(x)
    return out


class Intent(LenientModel):
    goal: str
    skill_level: str
    environment: list[str]
    values: list[str]
    hard_constraints: HardConstraints
    soft_preferences: list[str]

    @field_validator("environment", "values", "soft_preferences", mode="before")
    @classmethod
    def _lists(cls, v):
        return _drop_placeholders(_listify(v))

    @computed_field
    @property
    def constraint_count(self) -> int:
        n = 0
        n += 1 if self.goal else 0
        n += 1 if self.skill_level else 0
        n += 1 if self.environment else 0
        n += 1 if self.values else 0
        n += 1 if self.hard_constraints.budget_max else 0
        n += 1 if self.hard_constraints.deliver_by_days else 0
        return n


class ToolResultRef(BaseModel):
    tool_result_id: str
    sku: str


class ProposalItem(LenientModel):
    sku: str
    name: str
    price: float
    rationale: str
    satisfies: list[str]
    grounded_on: list[ToolResultRef]

    @field_validator("satisfies", mode="before")
    @classmethod
    def _lists(cls, v):
        return _listify(v)


class Alternative(LenientModel):
    sku: str
    name: str
    bundle_price: float
    tradeoff: str
    items: list[str] = Field(default_factory=list)  # every SKU in the alternative bundle; lets the gate price it exactly

    @field_validator("items", mode="before")
    @classmethod
    def _lists(cls, v):
        return _listify(v)


class Proposal(LenientModel):
    items: list[ProposalItem]
    bundle_price: float
    discount_pct: float
    intent_coverage: str
    alternative: Optional[Alternative] = None
    expires_at: str


class BuyerDecision(LenientModel):
    action: Literal["accept", "counter"]
    message: str
    counter_budget: Optional[float] = None


class Order(BaseModel):
    order_id: str
    skus: list[str]
    total: float
    mandate_id: str
    status: Literal["placed", "rejected"]


class SoftRules(BaseModel):
    negotiation_style: str
    allowed_claims: list[str]
    bundling: bool
    category_restrictions: list[str]
    pricing_guidance: str


class HardRules(BaseModel):
    max_discount_pct: float
    min_margin_pct: float
    category_overrides: dict[str, float] = Field(default_factory=dict)


class MerchantRules(BaseModel):
    soft: SoftRules
    hard: HardRules


class Event(BaseModel):
    id: int
    run_id: str
    ts: str
    lane: Lane
    type: EventType
    payload: dict
