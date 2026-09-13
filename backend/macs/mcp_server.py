from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP

from macs.store import Store

TZ = timezone(timedelta(hours=10))


def build_server(store: Store) -> FastMCP:
    mcp = FastMCP("retailer-systems")

    def _public(p: dict) -> dict:
        """Catalogue record without the stored embedding vector (not JSON-serialisable, not for the model)."""
        return {k: v for k, v in p.items() if k != "embedding"}

    def _product(sku: str) -> dict:
        p = store.get("catalogue", sku)
        if p is None:
            raise ValueError(f"unknown sku {sku}")
        return _public(p)

    @mcp.tool
    def search_products(type: str | None = None, max_price: float | None = None,
                        max_ship_days: int | None = None, suited_for: str | None = None,
                        sku_in: list[str] | None = None) -> list[dict]:
        """Filter the catalogue. Returns full product records that match every given filter."""
        out = []
        source = store.get_many("catalogue", sku_in) if sku_in is not None else store.list("catalogue")
        for p in source:
            if type and p["type"] != type:
                continue
            if max_price is not None and p["list_price"] > max_price:
                continue
            if max_ship_days is not None and p["ship_days"] > max_ship_days:
                continue
            if suited_for and suited_for not in p.get("suited_for", []):
                continue
            out.append(_public(p))
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
    def create_order(skus: list[str], mandate_id: str, total: float | None = None) -> dict:
        """Place an order at the agreed bundle price (list total when none is given). The only tool that writes."""
        products = [_product(s) for s in skus]
        total = total if total is not None else sum(p["list_price"] for p in products)
        ship_days = max((p["ship_days"] for p in products), default=0)
        order = {
            "order_id": "ord_" + uuid.uuid4().hex[:8], "skus": skus, "total": total,
            "mandate_id": mandate_id, "status": "placed", "ship_days": ship_days,
            "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
        }
        store.set("orders", order["order_id"], order)
        return {k: order[k] for k in ("order_id", "skus", "total", "mandate_id", "status", "ship_days")}

    return mcp
