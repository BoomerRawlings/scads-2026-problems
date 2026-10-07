"""Storage/publication/evidence checks for the local reference implementation.

These deterministic tests cover selected acceptance invariants. They are not
tests of actual model extraction, semantic retrieval quality, or large scale.
"""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from graphrag_discovery.engine import Engine
from graphrag_discovery.records import DomainError


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pump"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
CORPUS = MANIFEST["corpus_id"]


def load_batch(index):
    batch = MANIFEST["batches"][index]
    records = [json.loads(line) for line in (FIXTURE_ROOT / batch["records"]).read_text(encoding="utf-8").splitlines()]
    assertions = json.loads((FIXTURE_ROOT / batch["assertions"]).read_text(encoding="utf-8"))
    return batch, records, assertions


class MutableClock:
    def __init__(self, value="2025-01-05T10:00:00Z"):
        self.set(value)

    def set(self, value):
        self.value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    def __call__(self):
        return self.value


class FixtureIntegrityTests(unittest.TestCase):
    def test_authored_hashes_offsets_labels_and_supersession_targets(self):
        """Fixture truth comes from exact text and manually authored lineage."""
        seen_assertions = set()
        for index in range(len(MANIFEST["batches"])):
            batch, records, assertions = load_batch(index)
            self.assertLess(batch["ingested_at"], batch["prepared_at"])
            self.assertLess(batch["prepared_at"], batch["published_at"])
            by_version = {(r["document_id"], r["version_id"]): r for r in records}
            for record in records:
                if record["operation"] == "upsert":
                    digest = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
                    self.assertEqual(record["source_sha256"], digest)
                    self.assertEqual(record["content_sha256"], digest)
            for assertion in assertions:
                source = by_version[(assertion["document_id"], assertion["version_id"])]
                span = source["text"][assertion["start"]:assertion["end"]]
                self.assertEqual(assertion["text"], span)
                self.assertIn(assertion["subject_label"], span)
                self.assertIn(assertion["object_label"], span)
                self.assertTrue(set(assertion["supersedes"]).issubset(seen_assertions))
                self.assertNotIn(assertion["assertion_id"], seen_assertions)
                seen_assertions.add(assertion["assertion_id"])
        gold = json.loads((FIXTURE_ROOT / MANIFEST["gold"]).read_text(encoding="utf-8"))
        for state in gold["states"]:
            self.assertTrue(set(state["assertion_ids"]).issubset(seen_assertions))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clock = MutableClock()
        self.engine = Engine(Path(self.directory.name) / "test.sqlite3", clock=self.clock)
        self.addCleanup(self.engine.close)

    def publish_batch(self, index, *, graph=True):
        batch, records, assertions = load_batch(index)
        self.clock.set(batch["ingested_at"])
        job = self.engine.ingest(CORPUS, records, idempotency_key=batch["id"])
        if graph:
            self.clock.set(batch["prepared_at"])
            self.engine.stage_assertions(job["job_id"], assertions)
        self.clock.set(batch["published_at"])
        return self.engine.publish_snapshot(job["job_id"], label=batch["id"])

    def test_source_only_snapshot_is_searchable_but_not_graph_ready(self):
        """A03/A30: source-only and completed-empty are distinct profiles."""
        snapshot = self.publish_batch(0, graph=False)
        self.assertIn("lexical", snapshot["capabilities"])
        result = self.engine.search(CORPUS, "Pump P", snapshot_id=snapshot["snapshot_id"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["evidence"]["version_id"], "v1")
        with self.assertRaises(DomainError):
            self.engine.search(CORPUS, "Pump P", mode="graphrag")

    def test_source_receipt_does_not_backdate_snapshot_activation(self):
        """A31: even graph-free evidence requires activation at/before K."""
        snapshot = self.publish_batch(0, graph=False)
        visible = self.engine.search(CORPUS, "Pump P")
        chunk = visible["items"][0]["chunk_id"]
        earlier = self.engine.search(CORPUS, "Pump P", knowledge_cutoff="2025-01-05T10:02:00Z")
        self.assertEqual(earlier["items"], [])
        with self.assertRaises(DomainError):
            self.engine.get_evidence(CORPUS, snapshot["snapshot_id"], chunk_id=chunk,
                                     knowledge_cutoff="2025-01-05T10:02:00Z")

    def test_completed_empty_extraction_is_explicit_not_a_failure(self):
        _, records, _ = load_batch(0)
        job = self.engine.ingest(CORPUS, records, idempotency_key="empty-extraction")
        self.engine.stage_assertions(job["job_id"], [])
        snapshot = self.engine.publish_snapshot(job["job_id"])
        self.assertIn("assertions", snapshot["capabilities"])
        result = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        self.assertFalse(any(item.get("assertion_id") for item in result["items"]))
        self.assertEqual(len(self.engine.search(CORPUS, "Pump P")["items"]), 1)

    def test_ingestion_idempotency_key_reuses_job_and_does_not_duplicate(self):
        _, records, _ = load_batch(0)
        first = self.engine.ingest(CORPUS, records, idempotency_key="same-batch")
        second = self.engine.ingest(CORPUS, deepcopy(records), idempotency_key="same-batch")
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual(first["accepted"], 1)
        self.engine.publish_snapshot(first["job_id"])
        self.assertEqual(len(self.engine.search(CORPUS, "Pump P")["items"]), 1)

    def test_idempotency_key_cannot_be_reused_for_different_input(self):
        _, records, _ = load_batch(0)
        self.engine.ingest(CORPUS, records, idempotency_key="fixed-key")
        different = deepcopy(records)
        different[0]["event_id"] = "different-event"
        with self.assertRaises(DomainError):
            self.engine.ingest(CORPUS, different, idempotency_key="fixed-key")

    def test_mixed_invalid_batch_cannot_silently_publish_as_complete(self):
        """A02/A03: quarantined input requires explicit exclusion."""
        _, records, _ = load_batch(0)
        invalid = deepcopy(records[0])
        invalid.update(event_id="bad-hash-event", document_id="bad-hash-document", content_sha256="0" * 64)
        job = self.engine.ingest(CORPUS, records + [invalid], idempotency_key="mixed")
        self.assertEqual(job["accepted"], 1)
        self.assertEqual(job["rejected"], 1)
        with self.assertRaises(DomainError):
            self.engine.publish_snapshot(job["job_id"])
        snapshot = self.engine.publish_snapshot(job["job_id"], allow_exclusions=True)
        self.assertTrue(snapshot["coverage"])
        self.assertEqual(len(self.engine.search(CORPUS, "Pump P")["items"]), 1)

    def test_conflicting_bytes_cannot_replace_an_immutable_source_version(self):
        self.publish_batch(0, graph=False)
        _, records, _ = load_batch(0)
        replacement = deepcopy(records[0])
        replacement.update(event_id="attempted-overwrite", text="Operator Z operates Pump P.")
        replacement["source_sha256"] = replacement["content_sha256"] = hashlib.sha256(replacement["text"].encode()).hexdigest()
        job = self.engine.ingest(CORPUS, [replacement], idempotency_key="overwrite")
        self.assertEqual(job["rejected"], 1)
        self.assertEqual(job["accepted"], 0)
        result = self.engine.search(CORPUS, "Pump P")
        self.assertIn("Operator A", result["items"][0]["text"])

    def test_cancelled_job_cannot_publish_or_corrupt_previous_snapshot(self):
        first = self.publish_batch(0)
        batch, records, assertions = load_batch(1)
        self.clock.set(batch["ingested_at"])
        job = self.engine.ingest(CORPUS, records, idempotency_key="to-cancel")
        self.engine.stage_assertions(job["job_id"], assertions)
        self.engine.cancel_job(job["job_id"])
        self.assertEqual(self.engine.get_job(job["job_id"])["status"], "cancelled")
        with self.assertRaises(DomainError):
            self.engine.publish_snapshot(job["job_id"])
        result = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        self.assertEqual(result["scope"]["snapshot_id"], first["snapshot_id"])
        self.assertEqual({item["assertion_id"] for item in result["items"] if item.get("assertion_id")}, {"a-initial"})

    def test_source_revision_links_override_arrival_order_within_batch(self):
        _, initial, _ = load_batch(0)
        _, planned, _ = load_batch(1)
        self.clock.set("2025-01-20T10:00:00Z")
        job = self.engine.ingest(CORPUS, planned + initial, idempotency_key="reverse-order")
        self.assertEqual(job["accepted"], 2)
        self.engine.publish_snapshot(job["job_id"])
        current = self.engine.search(CORPUS, "Pump P")
        self.assertEqual({item["evidence"]["version_id"] for item in current["items"]}, {"v2"})

    def test_unicode_evidence_uses_codepoint_offsets_and_exact_source_text(self):
        """A05: an astral character distinguishes character from byte offsets."""
        _, records, assertions = load_batch(0)
        record, assertion = records[0], assertions[0]
        record["text"] = "Résumé: 💧 " + record["text"]
        digest = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
        record["source_sha256"] = record["content_sha256"] = digest
        assertion["start"] = record["text"].index(assertion["text"])
        assertion["end"] = assertion["start"] + len(assertion["text"])
        job = self.engine.ingest(CORPUS, [record], idempotency_key="unicode")
        self.engine.stage_assertions(job["job_id"], [assertion])
        snapshot = self.engine.publish_snapshot(job["job_id"])
        evidence = self.engine.get_evidence(CORPUS, snapshot["snapshot_id"], assertion_id="a-initial")
        self.assertEqual(evidence["text"], assertion["text"])
        self.assertEqual(evidence["start"], assertion["start"])
        self.assertEqual(evidence["end"], assertion["end"])
        self.assertEqual(evidence["source_uri"], record["source_uri"])

    def test_snapshot_scope_is_enforced_for_search_and_evidence(self):
        snapshot = self.publish_batch(0)
        with self.assertRaises(DomainError):
            self.engine.search("different-corpus", "Pump P", snapshot_id=snapshot["snapshot_id"])
        with self.assertRaises(DomainError):
            self.engine.get_evidence("different-corpus", snapshot["snapshot_id"], assertion_id="a-initial")

    def test_saved_run_remains_pinned_after_new_publication(self):
        first = self.publish_batch(0)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        self.publish_batch(1)
        saved = self.engine.get_run(run["run_id"])
        self.assertEqual(saved["scope"]["snapshot_id"], first["snapshot_id"])
        self.assertEqual(saved["items"], run["items"])

    def test_unknown_query_returns_no_invented_answer(self):
        self.publish_batch(0)
        result = self.engine.search(CORPUS, "unmentioned-zirconium", mode="graphrag")
        self.assertEqual(result["items"], [])

    def test_frozen_pages_do_not_duplicate_or_drift_after_publication(self):
        """A16: continuation pages enumerate a saved result, not a fresh query."""
        self.publish_batch(0)
        self.publish_batch(1)
        first = self.engine.search(CORPUS, "Pump P", mode="graphrag", page_size=1)
        cursor = first["next_cursor"]
        self.assertIsNotNone(cursor)
        expected = self.engine.get_run(first["run_id"])["items"]
        # Same-day empty publication changes latest without expiring the cursor.
        self.clock.set("2025-01-20T11:00:00Z")
        job = self.engine.ingest(CORPUS, load_batch(1)[1], idempotency_key="republish")
        self.engine.publish_snapshot(job["job_id"])
        page = self.engine.page(cursor, scope=first["scope"])
        repeated = self.engine.page(cursor, scope=first["scope"])
        self.assertEqual(page["items"], repeated["items"])
        self.assertEqual(page["scope"], first["scope"])
        self.assertEqual(first["items"] + page["items"], expected)
        self.assertEqual(len({item["id"] for item in expected}), len(expected))
        self.assertIsNone(page["next_cursor"])

    def test_cursor_rejects_changed_scope_unknown_and_expired_tokens(self):
        self.publish_batch(0)
        self.publish_batch(1)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag", page_size=1)
        changed = dict(run["scope"], valid_time="2025-02-02T00:00:00Z")
        with self.assertRaises(DomainError):
            self.engine.page(run["next_cursor"], scope=changed)
        with self.assertRaises(DomainError):
            self.engine.page("unknown-cursor")
        self.clock.set("2025-01-22T00:00:00Z")
        with self.assertRaises(DomainError):
            self.engine.page(run["next_cursor"])

    def test_scan_and_evidence_budgets_are_visible_and_enforced(self):
        self.publish_batch(0)
        no_scan = self.engine.search(CORPUS, "Pump P", mode="graphrag", budget={"max_scan": 0})
        self.assertTrue(no_scan["truncated"])
        self.assertEqual(no_scan["usage"]["scanned"], 0)
        self.assertEqual(no_scan["items"], [])
        no_context = self.engine.search(CORPUS, "Pump P", mode="graphrag", budget={"max_evidence_chars": 0})
        self.assertTrue(no_context["truncated"])
        self.assertEqual(no_context["items"], [])
        self.assertEqual(no_context["usage"]["evidence_chars"], 0)

    def test_zero_graph_edge_budget_reports_truncation(self):
        self.publish_batch(0)
        result = self.engine.search(CORPUS, "Pump P", mode="graphrag", budget={"max_edges": 0})
        self.assertEqual(result["items"], [])
        self.assertTrue(result["truncated"], "An edge cap must not resemble an exhaustive empty result")

    def test_failed_activation_rolls_back_and_preserves_previous_snapshot(self):
        """A04: a late lineage failure must not expose partially activated rows."""
        first = self.publish_batch(0)
        batch, records, assertions = load_batch(1)
        assertions[0]["supersedes"] = ["unpublished-assertion"]
        self.clock.set(batch["ingested_at"])
        job = self.engine.ingest(CORPUS, records, idempotency_key="invalid-lineage")
        self.engine.stage_assertions(job["job_id"], assertions)
        self.clock.set(batch["published_at"])
        with self.assertRaises(DomainError):
            self.engine.publish_snapshot(job["job_id"])
        current = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        self.assertEqual(current["scope"]["snapshot_id"], first["snapshot_id"])
        self.assertEqual({item["assertion_id"] for item in current["items"]}, {"a-initial"})
        self.assertIsNone(self.engine.get_job(job["job_id"])["snapshot_id"])

    def test_unsupported_world_time_lexical_query_rejects_instead_of_ignoring_filter(self):
        self.publish_batch(0, graph=False)
        with self.assertRaises(DomainError):
            self.engine.search(CORPUS, "Pump P", mode="lexical", valid_time="2025-01-10T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
