from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

Lane = Literal["merchant", "a2a", "system"]
EventType = Literal["message", "tool", "gate", "stage", "intent", "proposal", "order"]
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


class Intent(BaseModel):
    goal: str
    skill_level: str
    environment: list[str]
    values: list[str]
    hard_constraints: HardConstraints
    soft_preferences: list[str]

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


class ProposalItem(BaseModel):
    sku: str
    name: str
    price: float
    rationale: str
    satisfies: list[str]
    grounded_on: list[ToolResultRef]


class Alternative(BaseModel):
    sku: str
    name: str
    bundle_price: float
    tradeoff: str


class Proposal(BaseModel):
    items: list[ProposalItem]
    bundle_price: float
    discount_pct: float
    intent_coverage: str
    alternative: Optional[Alternative] = None
    expires_at: str


class BuyerDecision(BaseModel):
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
