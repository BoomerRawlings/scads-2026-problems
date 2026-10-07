"""Regression checks for publication, effective coverage, and saved workflows."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from graphrag_discovery.demo import SimulatedClock
from graphrag_discovery.engine import Engine
from graphrag_discovery.records import DomainError, text_hash
from tests.test_records import claim, source


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workflow.sqlite3"
        self.clock = SimulatedClock("2025-01-06T00:00:00Z")
        self.engine = Engine(self.path, self.clock)
        self.addCleanup(self.engine.close)

    def ingest(self, corpus="corpus", key="source"):
        return self.engine.ingest(corpus, [source()], key)["job_id"]

    def publish(self, corpus="corpus", *, graph=True, key="source"):
        job = self.ingest(corpus, key)
        if graph:
            self.engine.stage_assertions(job, [claim(source())])
        return self.engine.publish_snapshot(job)

    def graph_baseline(self, corpus="corpus"):
        run = self.engine.search(corpus, "Pump P", mode="graphrag")
        return self.engine.save_baseline(run["run_id"])

    def peer(self):
        peer = Engine(self.path, self.clock)
        self.addCleanup(peer.close)
        peer.db.execute("PRAGMA busy_timeout=0")
        return peer

    def test_last_source_withdrawal_remains_comparable_as_retraction(self):
        self.publish()
        baseline = self.graph_baseline()
        self.clock.set("2025-01-07T00:00:00Z")
        withdrawal = {"schema_version": "1", "event_id": "withdraw-1", "document_id": "doc",
                      "version_id": "v1", "operation": "withdraw", "reason": "Publisher withdrawal",
                      "access_scope": "public"}
        job = self.engine.ingest("corpus", [withdrawal], "withdraw")
        snapshot = self.engine.publish_snapshot(job["job_id"])
        self.assertEqual(snapshot["coverage"]["active_documents"], 0)
        compared = self.engine.compare(baseline["baseline_id"])
        self.assertFalse(compared["truncated"])
        self.assertEqual(len(compared["changes"]), 1)
        change = compared["changes"][0]
        self.assertIn("retraction", change["categories"])
        self.assertEqual([item["assertion_id"] for item in change["before"]], ["a-1"])
        self.assertEqual(change["after"], [])

    def test_historical_coverage_does_not_include_later_graph_publication(self):
        first = self.publish(graph=False)
        self.clock.set("2025-01-07T00:00:00Z")
        latest = self.publish(key="delayed-graph")
        historical = self.engine.search("corpus", "Pump P", mode="graphrag",
                                        knowledge_cutoff=first["published_at"])
        self.assertEqual(historical["scope"]["snapshot_id"], latest["snapshot_id"])
        self.assertEqual(historical["items"], [])
        self.assertEqual(historical["coverage"]["extraction"], {"pending": 1})
        self.assertFalse(historical["coverage"]["interpretation_complete"])
        current = self.engine.search("corpus", "Pump P", mode="graphrag")
        self.assertEqual(len(current["items"]), 1)
        self.assertEqual(current["coverage"]["extraction"], {"succeeded_with_assertions": 1})

    def test_malformed_staged_assertion_returns_domain_error_without_mutation(self):
        job = self.ingest()
        malformed = [None, "not an object", {}, {"document_id": "doc"},
                     {"document_id": [], "version_id": "v1", "processing_version": "plain-text-v1"}]
        for assertion in malformed:
            with self.subTest(assertion=assertion), self.assertRaises(DomainError) as caught:
                self.engine.stage_assertions(job, [assertion])
            self.assertEqual(caught.exception.code, "invalid_evidence")
        # A rejected request must not leave a transaction or partial staged batch.
        self.engine.stage_assertions(job, [claim(source())])
        self.engine.publish_snapshot(job)
        self.assertEqual(len(self.engine.search("corpus", "Pump P", mode="graphrag")["items"]), 1)

    def test_investigation_stale_write_cannot_replace_newer_notes(self):
        snapshot = self.publish()
        data = {"corpus_id": "corpus", "snapshot_id": snapshot["snapshot_id"],
                "title": "Pump history", "question": "Who operates Pump P?", "notes": "Initial note"}
        first = self.engine.save_investigation(data)
        update = dict(data, investigation_id=first["investigation_id"], notes=["Reviewed source", "Open question"])
        second = self.engine.save_investigation(update, expected_version=first["version"])
        with self.assertRaises(DomainError) as caught:
            self.engine.save_investigation(dict(update, notes="Stale replacement"), expected_version=first["version"])
        self.assertEqual(caught.exception.code, "version_conflict")
        self.assertEqual(second["version"], 2)
        self.assertEqual(self.engine.get_investigation(first["investigation_id"]), second)

    def test_investigation_rejects_cross_corpus_snapshot_run_and_baseline(self):
        own = self.publish()
        other = self.publish("other")
        baseline = self.graph_baseline("other")
        data = {"corpus_id": "corpus", "snapshot_id": own["snapshot_id"],
                "title": "Pump history", "question": "Who operates Pump P?"}
        for foreign in ({"snapshot_id": other["snapshot_id"]}, {"run_ids": [baseline["run_id"]]},
                        {"baseline_ids": [baseline["baseline_id"]]}):
            with self.subTest(foreign=foreign), self.assertRaises(DomainError) as caught:
                self.engine.save_investigation(dict(data, **foreign))
            self.assertEqual(caught.exception.code, "scope_mismatch")
        self.assertEqual(self.engine.list_investigations("corpus"), [])

    def test_export_checks_canonical_source_when_saved_text_and_hash_both_change(self):
        self.publish()
        run = self.engine.search("corpus", "Pump P", mode="graphrag")
        frozen = self.engine.get_run(run["run_id"])
        item = frozen["items"][0]
        item["text"] = item["text"].replace("A", "Z")
        item["evidence"]["text_hash"] = text_hash(item["text"])
        with self.engine.db:
            self.engine.db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(frozen), run["run_id"]))
        destination = Path(self.directory.name) / "tampered-export"
        with self.assertRaises(DomainError) as caught:
            self.engine.export_evidence(run["run_id"], destination)
        self.assertEqual(caught.exception.code, "evidence_integrity")
        self.assertFalse(destination.exists())

    def test_cancellation_locks_before_reading_job_state(self):
        job, peer = self.ingest(), self.peer()
        read, attempts = self.engine._one, []

        def interleave(table, identifier):
            if table == "jobs" and not attempts:
                attempts.append(identifier)
                with self.assertRaises(sqlite3.OperationalError):
                    peer.publish_snapshot(job)
            return read(table, identifier)

        with patch.object(self.engine, "_one", side_effect=interleave):
            cancelled = self.engine.cancel_job(job)
        self.assertEqual(attempts, [job])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(cancelled["snapshot_id"])
        with self.assertRaises(DomainError):
            peer.publish_snapshot(job)
        self.assertEqual(peer.list_snapshots("corpus"), [])

    def test_staging_rechecks_job_after_concurrent_publication(self):
        job, peer = self.ingest(), self.peer()
        read, published = self.engine._one, []

        def interleave(table, identifier):
            row = read(table, identifier)
            if table == "jobs" and not published:
                published.append(peer.publish_snapshot(job))
            return row

        with patch.object(self.engine, "_one", side_effect=interleave), self.assertRaises(DomainError) as caught:
            self.engine.stage_assertions(job, [claim(source())])
        self.assertEqual(caught.exception.code, "job_closed")
        self.assertEqual(len(published), 1)
        self.assertEqual(self.engine.get_job(job)["snapshot_id"], published[0]["snapshot_id"])
        self.assertEqual(published[0]["coverage"]["extraction"], {"pending": 1})
        self.assertIsNone(self.engine.db.execute("SELECT assertions FROM jobs WHERE id=?", (job,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
