"""Independent exact-vector truth, temporal eligibility, and artifact integrity."""
import json
from pathlib import Path
import tempfile
import unittest

from graphrag_discovery.engine import Engine
from graphrag_discovery.records import DomainError, text_hash
from graphrag_discovery.vectors import normalized_vector
from tests.test_records import source


PROFILE = {"provider": "authored-vectors", "model": "two-dimensional", "revision": "1"}


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "db.sqlite3"
        self.time = "2025-01-10T00:00:00Z"
        self.engine = Engine(self.path, lambda: self.time)
        self.addCleanup(self.engine.close)

    def publish(self, identifier, text):
        record = dict(source(), document_id=identifier, event_id=identifier, text=text,
                      source_sha256=text_hash(text), content_sha256=text_hash(text))
        job = self.engine.ingest("test", [record], identifier)
        return self.engine.publish_snapshot(job["job_id"])

    def index(self, vector_for_text):
        snapshot, items = self.engine.index_items("test")
        entries = [{"kind": i["kind"], "item_id": i["id"], "text_hash": text_hash(i["text"]), "vector": vector_for_text(i["text"])} for i in items]
        return self.engine.import_vectors("test", snapshot["snapshot_id"], PROFILE, entries), entries

    def query(self, index, **kw):
        return self.engine.search("test", "pump", mode="dense", vector_index_id=index["index_id"], query_vector=[1, 0], embedding_profile=PROFILE, **kw)

    def test_exact_cosine_matches_independent_order_and_ties(self):
        self.publish("a", "orthogonal")
        self.publish("b", "aligned")
        self.publish("c", "opposite")
        vectors = {"orthogonal": [0, 4], "aligned": [5, 0], "opposite": [-2, 0]}
        index, _ = self.index(vectors.__getitem__)
        result = self.query(index)
        self.assertEqual([i["evidence"]["document_id"] for i in result["items"]], ["b", "a", "c"])
        self.assertEqual([i["score"] for i in result["items"]], [1, 0, -1])
        self.assertFalse(result["truncated"])

    def test_future_vector_cannot_displace_eligible_past_evidence(self):
        old = self.publish("old", "old evidence")
        self.time = "2025-02-10T00:00:00Z"
        self.publish("future", "future evidence")
        index, _ = self.index(lambda text: [0, 1] if text.startswith("old") else [1, 0])
        result = self.query(index, knowledge_cutoff=old["published_at"], limit=1)
        self.assertEqual(result["items"][0]["evidence"]["document_id"], "old")
        self.assertFalse(result["truncated"])

    def test_withdrawn_text_remains_in_artifact_but_not_current_retrieval(self):
        self.publish("old", "pump")
        index, _ = self.index(lambda _: [1, 0])
        self.time = "2025-02-10T00:00:00Z"
        event = {"schema_version": "1", "operation": "withdraw", "event_id": "withdraw", "document_id": "old", "version_id": "v1", "reason": "withdrawn", "access_scope": "public"}
        job = self.engine.ingest("test", [event], "withdraw")
        self.engine.publish_snapshot(job["job_id"])
        self.assertEqual(self.query(index)["items"], [])

    def test_profile_dimension_and_corpus_mismatch_are_rejected(self):
        self.publish("a", "pump")
        index, _ = self.index(lambda _: [1, 0])
        for override in ({"embedding_profile": dict(PROFILE, revision="2")}, {"query_vector": [1, 0, 0]}):
            with self.subTest(override), self.assertRaises(DomainError):
                params = dict(vector_index_id=index["index_id"], query_vector=[1, 0], embedding_profile=PROFILE)
                self.engine.search("test", "pump", mode="dense", **(params | override))
        with self.assertRaises(DomainError):
            self.engine.get_vector_index(index["index_id"], "another")

    def test_atomic_import_rejects_missing_duplicate_or_wrong_hash(self):
        self.publish("a", "pump")
        snapshot, items = self.engine.index_items("test")
        entry = {"kind": "chunk", "item_id": items[0]["id"], "text_hash": "wrong", "vector": [1, 0]}
        for entries in ([], [entry], [entry, entry]):
            with self.subTest(entries), self.assertRaises(DomainError):
                self.engine.import_vectors("test", snapshot["snapshot_id"], PROFILE, entries)
        self.assertEqual(self.engine.list_vector_indexes("test"), [])

    def test_new_source_requires_new_artifact_without_silent_fallback(self):
        self.publish("a", "pump")
        index, _ = self.index(lambda _: [1, 0])
        self.publish("b", "later pump")
        with self.assertRaises(DomainError) as error:
            self.query(index)
        self.assertEqual(error.exception.code, "incomplete_vectors")

    def test_hybrid_explains_both_ranks_and_freezes_pages(self):
        self.publish("a", "pump")
        self.publish("b", "unrelated")
        index, _ = self.index(lambda text: [0, 1] if text == "pump" else [1, 0])
        result = self.engine.search("test", "pump", mode="hybrid", vector_index_id=index["index_id"], query_vector=[1, 0], embedding_profile=PROFILE, page_size=1)
        self.assertEqual(result["items"][0]["evidence"]["document_id"], "a")
        self.assertEqual(result["items"][0]["selection_reason"]["ranks"], {"lexical": 1, "dense": 2})
        self.publish("c", "new pump")
        page = self.engine.page(result["next_cursor"])
        self.assertEqual(page["items"][0]["evidence"]["document_id"], "b")
        self.assertEqual(page["scope"], result["scope"])
        baseline = self.engine.save_baseline(result["run_id"])
        compared = self.engine.compare(baseline["baseline_id"], mode="source_change")
        self.assertEqual(compared["changes"], [])

    def test_scan_budget_does_not_claim_exact_global_recall(self):
        self.publish("a", "pump")
        index, _ = self.index(lambda _: [1, 0])
        result = self.query(index, budget={"max_scan": 0})
        self.assertTrue(result["truncated"])
        self.assertEqual(result["items"], [])

    def test_nonfinite_zero_boolean_vectors_rejected(self):
        for vector in ([float("nan")], [float("inf")], [0, 0], [True, 1], [], [10**400, 1], [1e308, 1e308, 1e308, 1e308]):
            with self.subTest(vector), self.assertRaises(DomainError):
                normalized_vector(vector)

    def test_database_upgrade_backup_and_reopen_preserve_vectors(self):
        self.publish("a", "pump")
        index, _ = self.index(lambda _: [1, 0])
        backup = Path(self.directory.name) / "backup.sqlite3"
        self.engine.backup(backup)
        with Engine(backup) as restored:
            self.assertEqual(restored.doctor()["schema_version"], 2)
            self.assertTrue(restored.doctor()["ok"])
            self.assertEqual(restored.get_vector_index(index["index_id"]), index)
        with self.assertRaises(DomainError):
            self.engine.backup(backup)

    def test_projection_deadline_interrupts_and_connection_recovers(self):
        self.publish("a", "pump")
        with self.assertRaises(DomainError) as error:
            self.engine.search("test", "pump", budget={"max_request_wall_ms": 0})
        self.assertEqual(error.exception.code, "query_budget_exhausted")
        self.assertEqual(len(self.engine.search("test", "pump")["items"]), 1)
        self.assertTrue(self.engine.doctor()["ok"])

    def test_legacy_schema_upgrade_preserves_evidence_and_future_version_rejected(self):
        snapshot = self.publish("a", "pump")
        self.engine.db.execute("PRAGMA user_version=0")
        with Engine(self.path) as upgraded:
            self.assertEqual(upgraded.doctor()["schema_version"], 2)
            self.assertEqual(upgraded.get_snapshot(snapshot["snapshot_id"]), snapshot)
        self.engine.db.execute("PRAGMA user_version=999")
        with self.assertRaises(DomainError) as error:
            Engine(self.path)
        self.assertEqual(error.exception.code, "newer_database")
