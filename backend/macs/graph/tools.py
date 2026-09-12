from __future__ import annotations

import json
import time
from typing import Any

from fastmcp import Client

from macs.emitter import Emitter


class ToolCaller:
    def __init__(self, client: Client, emitter: Emitter) -> None:
        self._client = client
        self._em = emitter
        self.issued: set[str] = set()
        self._n = 0

    async def call(self, name: str, args: dict) -> tuple[Any, str]:
        self._n += 1
        tool_result_id = f"{self._em.run_id}-tool-{self._n}"
        t0 = time.perf_counter()
        result = await self._client.call_tool(name, args)
        latency = int((time.perf_counter() - t0) * 1000)
        data = result.data if result.data is not None else json.loads(result.content[0].text)
        self.issued.add(tool_result_id)
        self._em.emit("a2a", "tool", {
            "name": name, "args": args, "result_summary": _summarise(name, data),
            "latency_ms": latency, "tool_result_id": tool_result_id,
        })
        return data, tool_result_id


def _summarise(name: str, data: Any) -> str:
    if name == "semantic_search":
        return "top matches: " + ", ".join(f"{h['sku']} ({h['distance']:.3f})" for h in data[:5])
    if name == "search_products":
        return f"{len(data)} products after hard filters: " + ", ".join(p["sku"] for p in data[:8])
    if name == "get_shipping":
        return f"{data['sku']}: ships in {data['ship_days']} day{'s' if data['ship_days'] != 1 else ''}, {data['stock']} in stock"
    if name == "create_order":
        return f"order {data['order_id']} {data['status']}, total {data['total']}"
    return json.dumps(data)[:160]
