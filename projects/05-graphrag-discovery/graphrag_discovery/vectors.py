"""Immutable exact-vector artifacts; eligibility is decided before scoring."""
from __future__ import annotations

import json
import math
import time
import uuid

from .records import DomainError, canonical_hash, text_hash
from .model_budget import call_allowance

MAX_INDEX_ITEMS = 20_000
MAX_DIMENSIONS = 4096
MAX_VECTOR_CELLS = 4_000_000


def normalized_vector(value, dimensions=None):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_DIMENSIONS:
        raise DomainError("invalid_vector", "Expected a bounded nonempty vector")
    if dimensions is not None and len(value) != dimensions:
        raise DomainError("vector_dimension_mismatch", "Query and index dimensions differ")
    try:
        finite = all(type(x) in (int, float) and math.isfinite(x) for x in value)
    except (OverflowError, ValueError):
        finite = False
    if not finite:
        raise DomainError("invalid_vector", "Vector components must be finite numbers")
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm <= 1e-30:
        raise DomainError("invalid_vector", "Vector norm must be finite and nonzero")
    return [x / norm for x in value]


def cosine(left, right):
    return max(-1.0, min(1.0, math.fsum(a*b for a, b in zip(left, right))))


def ranked_fusion(items, *, dense_only=False):
    """Exact cosine ordering or RRF of lexical and dense rankings."""
    lexical = sorted((i for i in items if i["lexical_score"] > 0), key=lambda i: (-i["lexical_score"], i["id"]))
    dense = sorted(items, key=lambda i: (-i["dense_score"], i["id"]))
    scores, ranks = {}, {}
    for channel, values in (("lexical", lexical), ("dense", dense)):
        for rank, item in enumerate(values, 1):
            ranks.setdefault(item["id"], {})[channel] = rank
            scores[item["id"]] = scores.get(item["id"], 0) + 1 / (60 + rank)
    return sorted((dict(i, score=i["dense_score"] if dense_only else scores[i["id"]],
                        selection_reason={"channel": "exact_dense" if dense_only else "hybrid_rrf", "ranks": ranks[i["id"]],
                                          "cosine": i["dense_score"], "lexical_score": i["lexical_score"]})
                   for i in dense), key=lambda i: (-i["score"], i["id"]))


class VectorMixin:
    def search_local(self, corpus_id, query, *, vector_index_id, **kwargs):
        from .local_models import LocalModelClient
        index = self.get_vector_index(vector_index_id, corpus_id)
        if index["profile"]["provider"] != "llama.cpp":
            raise DomainError("unsupported_model", "This artifact requires a supplied query vector")
        if kwargs.get("mode", "lexical") == "lexical":
            raise DomainError("invalid_query", "Select dense, hybrid, or graphrag when using a vector index")
        bounds = self._budget(kwargs.get("budget"))
        if bounds["max_request_wall_ms"] == 0 or bounds["max_scan"] == 0:
            raise DomainError("query_budget_exhausted", "No allowance remains for query embedding; no model call made")
        # Validate scope before sending even a local model request.
        self._scope(corpus_id, kwargs.get("snapshot_id", "latest"), kwargs.get("knowledge_cutoff"))
        client = LocalModelClient.from_profile(index["profile"]["settings"])
        began = time.monotonic()
        client.timeout = min(client.timeout, bounds["max_request_wall_ms"] / 1000)
        response = client.embed([query])
        elapsed_ms = (time.monotonic()-began)*1000
        remaining = bounds["max_request_wall_ms"] - math.ceil(elapsed_ms)
        if remaining <= 0:
            raise DomainError("query_budget_exhausted", "Query embedding consumed the request allowance", {"model_calls": 1, "embedding": response["metadata"]})
        kwargs["budget"] = dict(bounds, max_request_wall_ms=remaining)
        result = self.search(corpus_id, query, vector_index_id=vector_index_id,
                             query_vector=response["vectors"][0], embedding_profile=index["profile"], **kwargs)
        # Store the single query-model call on the frozen run, so later pages do not call again.
        run = self.get_run(result["run_id"])
        run["usage"].update(model_calls=1, query_embedding=response["metadata"], elapsed_ms=round((time.monotonic()-began)*1000, 3))
        run["budget"] = bounds
        with self.db:
            self.db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(run, ensure_ascii=False, allow_nan=False), run["run_id"]))
        result["usage"] = run["usage"]
        result["budget"] = bounds
        return result

    def index_items(self, corpus_id, snapshot_id="latest"):
        """Include retained historical text for cutoff-safe reconstruction."""
        snapshot, cutoff = self._scope(corpus_id, snapshot_id, None)
        items = []
        for record in self._sources(snapshot, cutoff, history=True).values():
            for chunk in self._chunks(record):
                items.append(dict(chunk, kind="chunk"))
                if len(items) > MAX_INDEX_ITEMS:
                    raise DomainError("reference_capacity_exceeded", "Vector item count exceeds reference capacity")
        for assertion in self._assertions(snapshot, cutoff, history=True):
            items.append({"id": assertion["id"], "kind": "assertion", "text": assertion["text"]})
            if len(items) > MAX_INDEX_ITEMS:
                raise DomainError("reference_capacity_exceeded", "Vector item count exceeds reference capacity")
        return snapshot, sorted(items, key=lambda i: (i["kind"], i["id"]))

    def import_vectors(self, corpus_id, snapshot_id, profile, entries):
        """Publish a complete immutable artifact or reject it without side effects."""
        snapshot, items = self.index_items(corpus_id, snapshot_id)
        if not isinstance(profile, dict) or set(profile) - {"provider", "model", "revision", "endpoint", "settings"} or not all(isinstance(profile.get(k), str) and profile[k] for k in ("provider", "model", "revision")):
            raise DomainError("invalid_vector_profile", "Profile requires provider, model, and revision")
        if len(json.dumps(profile, allow_nan=False)) > 16384:
            raise DomainError("invalid_vector_profile", "Profile is too large")
        if not isinstance(entries, list) or len(entries) != len(items) or not entries:
            raise DomainError("incomplete_vectors", "Exactly one vector for every retained source/assertion item is required")
        expected = {(i["kind"], i["id"]): text_hash(i["text"]) for i in items}
        vectors, dimensions = {}, None
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"kind", "item_id", "text_hash", "vector"}:
                raise DomainError("invalid_vector", "Invalid vector entry fields")
            if entry["kind"] not in ("chunk", "assertion") or not isinstance(entry["item_id"], str):
                raise DomainError("invalid_vector", "Invalid vector item identity")
            key = (entry["kind"], entry["item_id"])
            if key not in expected or key in vectors or entry["text_hash"] != expected[key]:
                raise DomainError("vector_source_mismatch", "Vector must bind a unique immutable item and exact text hash")
            vector = normalized_vector(entry["vector"], dimensions)
            dimensions = len(vector)
            if dimensions * len(entries) > MAX_VECTOR_CELLS:
                raise DomainError("reference_capacity_exceeded", "Vector artifact exceeds the local cell budget")
            vectors[key] = vector
        identifier, created = "vectors_" + uuid.uuid4().hex, self._now()
        with self.db:
            self.db.execute("INSERT INTO vector_indexes VALUES(?,?,?,?,?,?,?)", (identifier, corpus_id, snapshot["snapshot_id"], created, json.dumps(profile, sort_keys=True), dimensions, len(vectors)))
            self.db.executemany("INSERT INTO vector_entries VALUES(?,?,?,?,?)", [(identifier, k[0], k[1], expected[k], json.dumps(v)) for k, v in vectors.items()])
        return self.get_vector_index(identifier, corpus_id)

    def get_vector_index(self, identifier, corpus_id=None):
        row = self.db.execute("SELECT * FROM vector_indexes WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Unknown vector index")
        if corpus_id is not None and row["corpus"] != corpus_id:
            raise DomainError("scope_mismatch", "Vector index belongs to another corpus")
        return {"index_id": row["id"], "corpus_id": row["corpus"], "snapshot_id": row["snapshot_id"], "created_at": row["created"], "profile": json.loads(row["profile"]), "dimensions": row["dimensions"], "item_count": row["item_count"], "algorithm": "exact-cosine", "replay": "cutoff-safe-text-reconstruction; not a historical ANN replay"}

    def list_vector_indexes(self, corpus_id):
        return [self.get_vector_index(row["id"], corpus_id) for row in self.db.execute("SELECT id FROM vector_indexes WHERE corpus=? ORDER BY rowid", (corpus_id,))]

    def _vector_query(self, index_id, corpus_id, query_vector, profile):
        index = self.get_vector_index(index_id, corpus_id)
        if profile != index["profile"]:
            raise DomainError("vector_profile_mismatch", "Query embedding profile must exactly match the frozen index")
        return index, normalized_vector(query_vector, index["dimensions"])

    def _item_vector(self, index_id, item):
        row = self.db.execute("SELECT vector,text_hash FROM vector_entries WHERE index_id=? AND kind=? AND item_id=?", (index_id, item["kind"], item["id"])).fetchone()
        if row is None or row["text_hash"] != text_hash(item["text"]):
            raise DomainError("incomplete_vectors", "Index is missing eligible evidence; build a new artifact for this snapshot")
        return json.loads(row["vector"])

    def build_vector_index(self, corpus_id, client, snapshot_id="latest", *, max_calls=100, max_wall_seconds=600):
        if type(max_calls) is not int or not 1 <= max_calls <= 1000 or type(max_wall_seconds) not in (int, float) or not 1 <= max_wall_seconds <= 3600:
            raise DomainError("invalid_budget", "Invalid local indexing allowance")
        snapshot, items = self.index_items(corpus_id, snapshot_id)
        profile = {"provider": "llama.cpp", "model": client.model, "revision": canonical_hash(client.profile), "endpoint": client.endpoint, "settings": client.profile}
        entries, calls, began, usage = [], 0, time.monotonic(), []
        for start in range(0, len(items), min(client.max_batch_size, 16)):
            if calls >= max_calls or time.monotonic()-began >= max_wall_seconds:
                raise DomainError("index_budget_exhausted", "No vector artifact published; increase the allowance for a new attempt", {"calls": calls})
            batch = items[start:start+min(client.max_batch_size, 16)]
            calls += 1
            with call_allowance(client, max_wall_seconds - (time.monotonic()-began)):
                output = client.embed([i["text"] for i in batch])
            usage.append(output["metadata"])
            if len(output["vectors"]) != len(batch):
                raise DomainError("invalid_model_output", "Embedding batch length mismatch")
            if output["vectors"] and len(normalized_vector(output["vectors"][0])) * len(items) > MAX_VECTOR_CELLS:
                raise DomainError("reference_capacity_exceeded", "Model dimension exceeds the total index cell allowance; no further calls dispatched", {"calls": calls})
            entries.extend({"kind": i["kind"], "item_id": i["id"], "text_hash": text_hash(i["text"]), "vector": v} for i, v in zip(batch, output["vectors"]))
        if time.monotonic()-began >= max_wall_seconds:
            raise DomainError("index_budget_exhausted", "Local call exceeded the indexing allowance; artifact not published", {"calls": calls})
        result = self.import_vectors(corpus_id, snapshot["snapshot_id"], profile, entries)
        return dict(result, usage={"model_calls": calls, "elapsed_ms": round((time.monotonic()-began)*1000, 3), "batches": usage})
