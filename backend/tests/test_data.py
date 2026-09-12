import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_hero_bundle_prices_produce_demo_numbers():
    cat = {p["sku"]: p for p in _load("catalogue.json")}
    hero = ["MIC-DYN-01", "IF-USB-02", "HP-REC-01", "ARM-DESK-01"]
    total = sum(cat[s]["list_price"] for s in hero)
    assert total == 692
    assert round(total * 0.85) == 588
    assert round(total * 0.78) == 540
    alt_total = total - cat["IF-USB-02"]["list_price"] + cat["IF-USB-01"]["list_price"]
    assert round(alt_total * 0.85) == 541
    cost = sum(cat[s]["cost"] for s in hero)
    assert (588 - cost) / 588 >= 0.20


def test_catalogue_has_required_fields_and_size():
    cat = _load("catalogue.json")
    assert 30 <= len(cat) <= 50
    required = {"sku", "name", "type", "list_price", "cost", "stock", "ship_days", "specs",
                "suited_for", "sustainability", "durability", "compatibility", "outcome_tags"}
    for p in cat:
        assert required <= set(p), p["sku"]
        assert p["ship_days"] >= 1


def test_governance_files():
    rules = _load("merchant_rules.json")
    assert rules["hard"]["max_discount_pct"] == 15
    assert rules["hard"]["min_margin_pct"] == 20
    mandates = {m["mandate_id"]: m for m in _load("mandates.json")}
    assert mandates["mandate-001"]["spend_cap"] is None
    assert mandates["mandate-002"]["spend_cap"] is None and mandates["mandate-002"]["expires_at"] > "2026-09-13"
    creds = {c["agent_id"] for c in _load("credentials.json")}
    assert "buyer-001" in creds and "buyer-999" not in creds
    assert len(_load("injection_patterns.json")["phrases"]) >= 5
