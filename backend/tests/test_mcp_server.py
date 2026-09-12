from fastmcp import Client

from macs.mcp_server import build_server


async def test_search_products_filters(seeded_store):
    async with Client(build_server(seeded_store)) as c:
        r = await c.call_tool("search_products", {"type": "microphone", "max_price": 200, "max_ship_days": 3})
        skus = {p["sku"] for p in r.data}
        assert "MIC-DYN-01" in skus and "MIC-DYN-02" not in skus


async def test_search_products_sku_in_and_suited_for(seeded_store):
    async with Client(build_server(seeded_store)) as c:
        r = await c.call_tool("search_products", {"sku_in": ["MIC-DYN-01", "HP-REC-01"], "suited_for": "noisy_room"})
        assert [p["sku"] for p in r.data] == ["MIC-DYN-01"]


async def test_semantic_search_returns_ranked_hits(seeded_store):
    async with Client(build_server(seeded_store)) as c:
        r = await c.call_tool("semantic_search", {"query_text": "beginner podcast noisy room sustainable", "k": 5})
        assert len(r.data) == 5
        assert all({"sku", "name", "distance"} <= set(h) for h in r.data)


async def test_get_tools(seeded_store):
    async with Client(build_server(seeded_store)) as c:
        assert (await c.call_tool("get_price", {"sku": "MIC-DYN-01"})).data == {"sku": "MIC-DYN-01", "list_price": 179, "cost": 110}
        assert (await c.call_tool("get_shipping", {"sku": "MIC-DYN-01"})).data == {"sku": "MIC-DYN-01", "ship_days": 2, "stock": 12}
        assert (await c.call_tool("get_product", {"sku": "MIC-DYN-01"})).data["name"].startswith("Northwind")


async def test_create_order_writes(seeded_store):
    async with Client(build_server(seeded_store)) as c:
        r = await c.call_tool("create_order", {"skus": ["MIC-DYN-01", "HP-REC-01"], "mandate_id": "mandate-001"})
        assert r.data["status"] == "placed" and r.data["total"] == 328
        assert seeded_store.get("orders", r.data["order_id"])["mandate_id"] == "mandate-001"
