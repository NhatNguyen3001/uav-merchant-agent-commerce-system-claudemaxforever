from typing import Any, Optional, TypedDict


class RunState(TypedDict, total=False):
    scenario: str
    request: dict
    credential: Optional[dict]
    mandate: Optional[dict]
    intent: Optional[dict]
    candidates: dict[str, dict]          # sku -> product record
    proposal: Optional[dict]
    gate_results: list[dict]
    negotiation_round: int
    buyer_reply: Optional[dict]
    order: Optional[dict]
    blocked: bool
    counter_budget: Optional[float]
    round_fixture_suffix: Any
