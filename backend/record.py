"""Run a scenario live and save it as a golden replay file.
Usage: python record.py --project merchant-agent-commerce-system --scenario happy_path [--fake]"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from macs.emitter import RunRegistry
from macs.graph.build import new_run_id, run_scenario
from macs.llm import LLM
from macs.scenarios import SCENARIOS
from macs.store import FirestoreStore, MemoryStore, VertexEmbedder

DATA = Path(__file__).resolve().parents[1] / "data"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    ap.add_argument("--fake", action="store_true", help="use FAKE_LLM fixtures and the in-memory store")
    a = ap.parse_args()

    if a.fake:
        from macs.seeddata import load_seed
        store, llm = load_seed(MemoryStore()), LLM(fake=True)
    else:
        store, llm = FirestoreStore(a.project, VertexEmbedder(a.project)), LLM(fake=False)

    reg = RunRegistry()
    run_id = new_run_id()
    await run_scenario(a.scenario, run_id, store, llm, reg)
    run = store.get("runs", run_id)
    if run["status"] != "finished":
        raise SystemExit(f"run {run_id} ended with status {run['status']}; not recording")

    golden_id = f"golden_{a.scenario}"
    events = []
    for ev in store.list_events(run_id):
        ev = dict(ev)
        ev["run_id"] = golden_id
        events.append(ev)
    run.update({"run_id": golden_id, "is_golden": True, "recorded_with": "fake" if a.fake else "live"})

    out = DATA / "replay" / f"{a.scenario}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run": run, "events": events}, indent=2), encoding="utf-8")
    print(f"recorded {len(events)} events from {run_id} to {out}")


if __name__ == "__main__":
    asyncio.run(main())
