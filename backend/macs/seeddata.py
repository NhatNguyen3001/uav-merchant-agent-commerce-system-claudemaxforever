from __future__ import annotations

import json
from pathlib import Path

from macs.store import Store

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data"


def load_seed(store: Store, data_dir: Path | None = None, catalogues: list[str] | None = None) -> Store:
    data = data_dir or DEFAULT_DATA

    def j(name):
        return json.loads((data / name).read_text(encoding="utf-8"))

    for name in catalogues or ["catalogue.json"]:
        for p in j(name):
            store.set("catalogue", p["sku"], p)
    store.set("merchant_rules", "current", j("merchant_rules.json"))
    for m in j("mandates.json"):
        store.set("mandates", m["mandate_id"], m)
    for c in j("credentials.json"):
        store.set("credentials", c["agent_id"], c)
    store.set("injection_patterns", "current", j("injection_patterns.json"))
    return store
