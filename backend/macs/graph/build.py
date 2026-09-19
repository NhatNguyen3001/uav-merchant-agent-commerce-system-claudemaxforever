from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastmcp import Client
from langgraph.graph import END, START, StateGraph

from macs.emitter import TZ, Emitter, RunRegistry
from macs.graph.nodes import make_nodes
from macs.graph.state import RunState
from macs.graph.tools import ToolCaller
from macs.llm import LLM
from macs.mcp_server import build_server
from macs.store import Store

log = logging.getLogger(__name__)
MAX_ROUNDS = 2


def new_run_id() -> str:
    return "run_" + datetime.now(TZ).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]


def build_graph(nodes: dict):
    g = StateGraph(RunState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.add_edge(START, "protocol_adapter")
    g.add_edge("protocol_adapter", "inbound_gate")
    g.add_conditional_edges("inbound_gate", lambda s: END if s.get("blocked") else "decode_intent")
    g.add_edge("decode_intent", "match_catalogue")
    g.add_conditional_edges("match_catalogue", lambda s: END if s.get("blocked") else "compose_proposal")
    g.add_conditional_edges("compose_proposal", lambda s: END if s.get("blocked") else "outbound_gate")
    g.add_conditional_edges("outbound_gate", lambda s: END if s.get("blocked") else "negotiate")
    g.add_conditional_edges(
        "negotiate",
        lambda s: "compose_proposal"
        if s.get("buyer_reply", {}).get("action") == "counter" and s["negotiation_round"] < MAX_ROUNDS
        else "execution_gate",
    )
    g.add_edge("execution_gate", END)
    return g.compile()


def _summary(state: dict) -> dict:
    order = state.get("order") or {}
    proposal = state.get("proposal") or {}
    return {
        "order_status": order.get("status", "none"),
        "bundle_price": proposal.get("bundle_price"),
        "gate_verdicts": state.get("gate_results", []),
    }


async def run_scenario(scenario: str, run_id: str, store: Store, llm: LLM, registry: RunRegistry,
                       now: datetime | None = None, input: dict | None = None, owner: str | None = None) -> dict:
    """Execute a canned scenario, or a custom ACP-shaped `input` (scenario label then becomes 'custom').
    `owner` is the hashed browser session that started the run; only that session can see it."""
    now = now or datetime.now(TZ)
    if not registry.has(run_id):
        registry.open(run_id, owner)
    doc = {"run_id": run_id, "scenario": scenario, "started_at": now.isoformat(timespec="seconds"),
           "finished_at": None, "status": "running", "is_golden": False, "summary": {}, "owner": owner}
    if input is not None:
        doc.update({"agent_id": input["agent_id"], "query": input["messages"][-1]["content"]})
    store.set("runs", run_id, doc)
    em = Emitter(run_id, store, registry)
    state: dict = {"scenario": scenario, "input": input, "gate_results": [], "negotiation_round": 0,
                   "blocked": False, "candidates": {}}
    status = "finished"
    try:
        async with Client(build_server(store)) as client:
            tools = ToolCaller(client, em)
            graph = build_graph(make_nodes(store, llm, tools, em, now))
            state = await graph.ainvoke(state)
    except Exception as e:  # noqa: BLE001 - any node failure ends the run visibly
        log.exception("run %s failed", run_id)
        em.stage(em.current_stage, "blocked", f"error: {type(e).__name__}: {e}"[:300])
        status = "failed"
    finally:
        run = store.get("runs", run_id) or {}
        run.update({"status": status, "finished_at": datetime.now(TZ).isoformat(timespec="seconds"),
                    "summary": _summary(state)})
        store.set("runs", run_id, run)
        registry.finish(run_id)
    return state
