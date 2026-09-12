from macs.store import MemoryStore, product_text


def _product(sku, name, tags):
    return {"sku": sku, "name": name, "type": "microphone", "list_price": 100, "cost": 60,
            "stock": 5, "ship_days": 2, "specs": {}, "suited_for": tags, "sustainability": {},
            "durability": "good", "compatibility": [], "outcome_tags": tags}


def test_set_get_list_roundtrip():
    s = MemoryStore()
    s.set("catalogue", "A", _product("A", "Alpha mic", ["beginner"]))
    assert s.get("catalogue", "A")["name"] == "Alpha mic"
    assert s.get("catalogue", "missing") is None
    assert [p["sku"] for p in s.list("catalogue")] == ["A"]


def test_events_are_returned_in_id_order():
    s = MemoryStore()
    s.set("runs", "r1", {"run_id": "r1", "status": "running"})
    s.add_event("r1", {"id": 2, "type": "stage"})
    s.add_event("r1", {"id": 1, "type": "message"})
    assert [e["id"] for e in s.list_events("r1")] == [1, 2]
    assert s.list_runs()[0]["run_id"] == "r1"


def test_nearest_uses_keyword_overlap_and_returns_distance():
    s = MemoryStore()
    s.set("catalogue", "A", _product("A", "Quiet dynamic mic", ["noisy_room", "beginner"]))
    s.set("catalogue", "B", _product("B", "Studio condenser mic", ["treated_room"]))
    hits = s.nearest("beginner podcast in a noisy room", k=2)
    assert hits[0]["sku"] == "A"
    assert hits[0]["distance"] < hits[1]["distance"]
    assert set(hits[0]) == {"sku", "name", "distance"}


def test_product_text_includes_reasoning_fields():
    t = product_text(_product("A", "Alpha", ["beginner"]))
    assert "Alpha" in t and "beginner" in t and "microphone" in t
