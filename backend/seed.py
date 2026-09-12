"""Seed Firestore from data/. Usage: python seed.py --project merchant-agent-commerce-system [--no-embed] [--golden-only]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from google.cloud.firestore_v1.vector import Vector

from macs.store import FirestoreStore, VertexEmbedder, product_text

DATA = Path(__file__).resolve().parents[1] / "data"


def j(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def seed_governance(store: FirestoreStore) -> None:
    store.set("merchant_rules", "current", j("merchant_rules.json"))
    for m in j("mandates.json"):
        store.set("mandates", m["mandate_id"], m)
    for c in j("credentials.json"):
        store.set("credentials", c["agent_id"], c)
    store.set("injection_patterns", "current", j("injection_patterns.json"))
    print("governance seeded")


def seed_catalogue(store: FirestoreStore, embedder: VertexEmbedder | None, files: list[str]) -> None:
    products, seen = [], set()
    for name in files:
        for p in j(name):
            if p["sku"] not in seen:
                seen.add(p["sku"]); products.append(p)
    vectors: list = []
    if embedder:
        for i in range(0, len(products), 100):  # Vertex accepts up to ~250 texts per call; stay well under
            vectors.extend(embedder.embed([product_text(p) for p in products[i:i + 100]]))
    else:
        vectors = [None] * len(products)
    for p, v in zip(products, vectors):
        doc = dict(p)
        if v is not None:
            doc["embedding"] = Vector(v)
        store.set("catalogue", p["sku"], doc)
    print(f"catalogue seeded: {len(products)} products from {files}, embedded={embedder is not None}")


def seed_golden(store: FirestoreStore) -> None:
    replay_dir = DATA / "replay"
    if not replay_dir.exists():
        print("no replay dir; skipping golden runs")
        return
    for path in sorted(replay_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        run = rec["run"]
        run["is_golden"] = True
        store.set("runs", run["run_id"], run)
        for ev in rec["events"]:
            store.add_event(run["run_id"], ev)
        print(f"golden run {run['run_id']} ({run['scenario']}) seeded with {len(rec['events'])} events")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--golden-only", action="store_true")
    ap.add_argument("--catalogue", action="append", default=None,
                    help="catalogue file(s) under data/; default catalogue.json (repeatable)")
    a = ap.parse_args()
    embedder = None if a.no_embed else VertexEmbedder(a.project)
    store = FirestoreStore(a.project, embedder)
    if not a.golden_only:
        seed_governance(store)
        seed_catalogue(store, embedder, a.catalogue or ["catalogue.json"])
    seed_golden(store)


if __name__ == "__main__":
    main()
