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


def test_intent_accepts_scalar_where_list_expected():
    intent = Intent(goal="g", skill_level="beginner", environment="noisy street", values="Sustainability",
                    hard_constraints={"budget_max": 600, "deliver_by_days": 7}, soft_preferences=None)
    assert intent.values == ["Sustainability"] and intent.environment == ["noisy street"] and intent.soft_preferences == []


def test_proposal_accepts_json_encoded_items_string():
    import json
    items = [{"sku": "A", "name": "a", "price": 1, "rationale": "r", "satisfies": "goal",
              "grounded_on": [{"tool_result_id": "t", "sku": "A"}]}]
    p = Proposal(items=json.dumps(items), bundle_price=1, discount_pct=0, intent_coverage="1/6",
                 alternative='{"sku": "B", "name": "b", "bundle_price": 2, "tradeoff": "x"}', expires_at="2026-09-13T00:00:00+10:00")
    assert p.items[0].sku == "A" and p.items[0].satisfies == ["goal"] and p.alternative.sku == "B"


def test_intent_drops_placeholder_entries():
    intent = Intent(goal="g", skill_level="beginner", environment=["<UNKNOWN>", "noisy street"], values=["unknown"],
                    hard_constraints={"budget_max": 300, "deliver_by_days": 3}, soft_preferences=["N/A", "not specified", ""])
    assert intent.environment == ["noisy street"] and intent.values == [] and intent.soft_preferences == []
    assert intent.constraint_count == 5
