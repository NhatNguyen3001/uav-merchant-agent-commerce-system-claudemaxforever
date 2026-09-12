from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP

from macs.store import Store

TZ = timezone(timedelta(hours=10))


def build_server(store: Store) -> FastMCP:
    mcp = FastMCP("retailer-systems")

    def _product(sku: str) -> dict:
        p = store.get("catalogue", sku)
        if p is None:
            raise ValueError(f"unknown sku {sku}")
        return p

    @mcp.tool
    def search_products(type: str | None = None, max_price: float | None = None,
                        max_ship_days: int | None = None, suited_for: str | None = None,
                        sku_in: list[str] | None = None) -> list[dict]:
        """Filter the catalogue. Returns full product records that match every given filter."""
        out = []
        for p in store.list("catalogue"):
            if type and p["type"] != type:
                continue
            if max_price is not None and p["list_price"] > max_price:
                continue
            if max_ship_days is not None and p["ship_days"] > max_ship_days:
                continue
            if suited_for and suited_for not in p.get("suited_for", []):
                continue
            if sku_in is not None and p["sku"] not in sku_in:
                continue
            out.append(p)
        return out

    @mcp.tool
    def semantic_search(query_text: str, k: int = 15) -> list[dict]:
        """Nearest products to a natural-language need. Returns sku, name, distance (lower is closer)."""
        return store.nearest(query_text, k)

    @mcp.tool
    def get_product(sku: str) -> dict:
        """Full product record for one SKU."""
        return _product(sku)

    @mcp.tool
    def get_price(sku: str) -> dict:
        """List price and cost for one SKU."""
        p = _product(sku)
        return {"sku": sku, "list_price": p["list_price"], "cost": p["cost"]}

    @mcp.tool
    def get_shipping(sku: str) -> dict:
        """Ship days and stock for one SKU."""
        p = _product(sku)
        return {"sku": sku, "ship_days": p["ship_days"], "stock": p["stock"]}

    @mcp.tool
    def create_order(skus: list[str], mandate_id: str) -> dict:
        """Place an order. The only tool that writes."""
        total = sum(_product(s)["list_price"] for s in skus)
        order = {
            "order_id": "ord_" + uuid.uuid4().hex[:8], "skus": skus, "total": total,
            "mandate_id": mandate_id, "status": "placed",
            "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
        }
        store.set("orders", order["order_id"], order)
        return {k: order[k] for k in ("order_id", "skus", "total", "mandate_id", "status")}

    return mcp
