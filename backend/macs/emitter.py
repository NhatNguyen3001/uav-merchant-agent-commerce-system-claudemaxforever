from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from macs.models import Event
from macs.store import Store

TZ = timezone(timedelta(hours=10))
GATE_STAGE = {"inbound": "inbound_gate", "catalogue": "proposal_engine", "outbound": "outbound_gate", "execution": "execution_gate"}


class RunRegistry:
    """In-memory per-run event buffer with asyncio wakeups for SSE consumers."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}
        self._done: set[str] = set()
        self._signals: dict[str, asyncio.Event] = {}
        self._owners: dict[str, str | None] = {}

    def open(self, run_id: str, owner: str | None = None) -> None:
        """`owner` is the hashed session that started the run; recorded before the run starts so a stream
        request that races the first Firestore write is still checked."""
        self._events[run_id] = []
        self._signals[run_id] = asyncio.Event()
        self._owners[run_id] = owner

    def has(self, run_id: str) -> bool:
        return run_id in self._events

    def owner(self, run_id: str) -> str | None:
        return self._owners.get(run_id)

    def publish(self, run_id: str, event: dict) -> None:
        self._events[run_id].append(event)
        self._signals[run_id].set()

    def events(self, run_id: str) -> list[dict]:
        return list(self._events.get(run_id, []))

    def finish(self, run_id: str) -> None:
        self._done.add(run_id)
        self._signals[run_id].set()

    def is_done(self, run_id: str) -> bool:
        return run_id in self._done

    async def wait(self, run_id: str) -> None:
        sig = self._signals[run_id]
        await sig.wait()
        sig.clear()


class Emitter:
    def __init__(self, run_id: str, store: Store, registry: RunRegistry) -> None:
        self.run_id = run_id
        self._store = store
        self._registry = registry
        self._n = 0
        self.current_stage = "protocol_adapter"

    @staticmethod
    def now() -> str:
        return datetime.now(TZ).isoformat(timespec="milliseconds")

    def emit(self, lane: str, type: str, payload: dict) -> dict:
        self._n += 1
        ev = Event(id=self._n, run_id=self.run_id, ts=self.now(), lane=lane, type=type, payload=payload).model_dump()
        self._store.add_event(self.run_id, ev)
        self._registry.publish(self.run_id, ev)
        return ev

    def stage(self, stage: str, status: str, note: str = "") -> dict:
        if status == "running":
            self.current_stage = stage
        return self.emit("system", "stage", {"stage": stage, "status": status, "note": note})

    def message(self, sender: str, text: str) -> dict:
        return self.emit("a2a", "message", {"from": sender, "text": text})

    def gate(self, gate: str, verdict: str, reason: str, before: dict | None = None, after: dict | None = None) -> dict:
        ev = self.emit("a2a", "gate", {"gate": gate, "verdict": verdict, "reason": reason, "before": before, "after": after})
        stage = GATE_STAGE[gate]
        if verdict == "blocked":
            self.stage(stage, "blocked", reason)
        elif gate == "catalogue":
            self.stage(stage, "running", reason)  # the proposal engine is still working after the catalogue check
        else:
            self.stage(stage, "passed", reason)
        return ev
