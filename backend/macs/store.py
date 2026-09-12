from __future__ import annotations

import re
from typing import Protocol


def product_text(p: dict) -> str:
    sus = p.get("sustainability") or {}
    parts = [
        p.get("name", ""), p.get("type", ""),
        "suited for " + ", ".join(p.get("suited_for", [])),
        "outcomes " + ", ".join(p.get("outcome_tags", [])),
        "materials " + ", ".join(sus.get("materials", [])),
        "certifications " + ", ".join(sus.get("certifications", [])),
        "brand practice " + str(sus.get("brand_practice", "")),
        "durability " + str(p.get("durability", "")),
    ]
    return ". ".join(x for x in parts if x)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Store(Protocol):
    def get(self, collection: str, doc_id: str) -> dict | None: ...
    def set(self, collection: str, doc_id: str, data: dict) -> None: ...
    def list(self, collection: str) -> list[dict]: ...
    def add_event(self, run_id: str, event: dict) -> None: ...
    def list_events(self, run_id: str) -> list[dict]: ...
    def list_runs(self) -> list[dict]: ...
    def delete_run(self, run_id: str) -> None: ...
    def nearest(self, query_text: str, k: int) -> list[dict]: ...


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower().replace("_", " ")))


def keyword_nearest(products: list[dict], query_text: str, k: int) -> list[dict]:
    """Offline stand-in for vector search: rank by token overlap, distance = 1/(1+overlap)."""
    q = _tokens(query_text)
    scored = []
    for p in products:
        overlap = len(q & _tokens(product_text(p)))
        scored.append((1.0 / (1 + overlap), p))
    scored.sort(key=lambda t: t[0])
    return [{"sku": p["sku"], "name": p["name"], "distance": round(d, 4)} for d, p in scored[:k]]


class MemoryStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict]] = {}
        self._events: dict[str, list[dict]] = {}

    def get(self, collection, doc_id):
        d = self._docs.get(collection, {}).get(doc_id)
        return dict(d) if d is not None else None

    def set(self, collection, doc_id, data):
        self._docs.setdefault(collection, {})[doc_id] = dict(data)

    def list(self, collection):
        return [dict(d) for d in self._docs.get(collection, {}).values()]

    def add_event(self, run_id, event):
        self._events.setdefault(run_id, []).append(dict(event))

    def list_events(self, run_id):
        return sorted((dict(e) for e in self._events.get(run_id, [])), key=lambda e: e["id"])

    def list_runs(self):
        return self.list("runs")

    def delete_run(self, run_id):
        self._docs.get("runs", {}).pop(run_id, None)
        self._events.pop(run_id, None)

    def nearest(self, query_text, k):
        return keyword_nearest(self.list("catalogue"), query_text, k)


class VertexEmbedder:
    MODEL = "text-embedding-005"
    DIM = 768

    def __init__(self, project: str, location: str = "australia-southeast1") -> None:
        from google import genai
        self._client = genai.Client(vertexai=True, project=project, location=location)

    def embed(self, texts):
        from google.genai import types
        resp = self._client.models.embed_content(
            model=self.MODEL, contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=self.DIM),
        )
        return [e.values for e in resp.embeddings]


class FirestoreStore:
    def __init__(self, project: str, embedder: Embedder | None = None) -> None:
        from google.cloud import firestore
        self._db = firestore.Client(project=project)
        self._embedder = embedder

    def get(self, collection, doc_id):
        snap = self._db.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def set(self, collection, doc_id, data):
        self._db.collection(collection).document(doc_id).set(data)

    def list(self, collection):
        return [d.to_dict() for d in self._db.collection(collection).stream()]

    def add_event(self, run_id, event):
        self._db.collection("runs").document(run_id).collection("events") \
            .document(f"{event['id']:05d}").set(event)

    def list_events(self, run_id):
        col = self._db.collection("runs").document(run_id).collection("events")
        return sorted((d.to_dict() for d in col.stream()), key=lambda e: e["id"])

    def list_runs(self):
        return self.list("runs")

    def delete_run(self, run_id):
        doc = self._db.collection("runs").document(run_id)
        batch = self._db.batch()
        for ev in doc.collection("events").stream():
            batch.delete(ev.reference)
        batch.delete(doc)
        batch.commit()

    def nearest(self, query_text, k):
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector
        if self._embedder is None:
            # FAKE_LLM mode against Firestore: keyword ranking over the stored catalogue, no Vertex call.
            return keyword_nearest(self.list("catalogue"), query_text, k)
        qv = self._embedder.embed([query_text])[0]
        query = self._db.collection("catalogue").find_nearest(
            vector_field="embedding", query_vector=Vector(qv),
            distance_measure=DistanceMeasure.COSINE, limit=k,
            distance_result_field="distance",
        )
        out = []
        for snap in query.get():
            d = snap.to_dict()
            out.append({"sku": d["sku"], "name": d["name"], "distance": round(float(d.get("distance", 0.0)), 4)})
        return out
