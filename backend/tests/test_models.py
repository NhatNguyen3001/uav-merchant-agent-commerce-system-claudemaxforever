from macs.models import (
    Event, Intent, Proposal, ProposalItem, ToolResultRef, Order, MerchantRules,
)


def test_intent_constraint_count_counts_all_non_empty_facets():
    intent = Intent(
        goal="record podcast", skill_level="beginner",
        environment=["noisy", "small"], values=["sustainable"],
        hard_constraints={"budget_max": 600, "deliver_by_days": 7},
        soft_preferences=["simple setup"],
    )
    assert intent.constraint_count == 6


def test_proposal_validates_nested_alternative():
    item = ProposalItem(sku="MIC-DYN-01", name="mic", price=179, rationale="r",
                        satisfies=["environment"], grounded_on=[ToolResultRef(tool_result_id="t1", sku="MIC-DYN-01")])
    p = Proposal(items=[item], bundle_price=179, discount_pct=0, intent_coverage="1/6",
                 alternative=None, expires_at="2026-09-12T23:59:59+10:00")
    assert p.items[0].grounded_on[0].tool_result_id == "t1"


def test_event_rejects_bad_lane():
    import pytest
    with pytest.raises(Exception):
        Event(id=1, run_id="r", ts="2026-09-12T09:00:00+10:00", lane="nope", type="stage", payload={})


def test_merchant_rules_split_soft_and_hard():
    rules = MerchantRules(
        soft={"negotiation_style": "friendly", "allowed_claims": ["certified"],
              "bundling": True, "category_restrictions": [], "pricing_guidance": "x"},
        hard={"max_discount_pct": 15, "min_margin_pct": 20, "category_overrides": {}},
    )
    assert rules.hard.max_discount_pct == 15
