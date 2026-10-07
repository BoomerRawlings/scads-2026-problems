"""Ephemeral typing previews preserve committed search and temporal boundaries."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from graphrag_discovery.engine import Engine
from graphrag_discovery.records import DomainError, text_hash
from graphrag_discovery.resources import read_text


MANIFEST = json.loads(read_text("fixtures", "pump", "manifest.json"))
CORPUS = MANIFEST["corpus_id"]


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.time = "2025-01-05T10:00:00Z"
        self.engine = Engine(":memory:", clock=lambda: self.time)
        self.addCleanup(self.engine.close)

    def batch(self, index, graph=True):
        entry = MANIFEST["batches"][index]
        records = [json.loads(line) for line in read_text("fixtures", "pump", entry["records"]).splitlines()]
        self.time = entry["ingested_at"]
        job = self.engine.ingest(CORPUS, records, entry["id"])
        if graph:
            self.time = entry["prepared_at"]
            self.engine.stage_assertions(job["job_id"], json.loads(read_text("fixtures", "pump", entry["assertions"])))
        self.time = entry["published_at"]
        return self.engine.publish_snapshot(job["job_id"])

    def test_preview_is_read_only_and_cannot_dispatch_vectors(self):
        self.batch(0)
        committed = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        before = tuple(self.engine.db.iterdump())
        with patch.object(self.engine, "_save_run", side_effect=AssertionError("Saved a preview")), \
             patch.object(self.engine, "_page", side_effect=AssertionError("Paged a preview")), \
             patch.object(self.engine, "_vector_query", side_effect=AssertionError("Preview used vectors")):
            for mode in ("lexical", "graphrag"):
                result = self.engine.preview(CORPUS, "Pum", mode=mode)
                self.assertEqual(result["operation"], "preview")
                self.assertEqual(result["usage"]["model_calls"], 0)
                self.assertNotIn("run_id", result)
                self.assertNotIn("next_cursor", result)
                self.assertNotIn("page_size", result)
                self.assertTrue(result["items"])
        self.assertEqual(tuple(self.engine.db.iterdump()), before)
        self.assertEqual(self.engine.get_run(committed["run_id"])["items"], committed["items"])

    def test_last_partial_word_matches_without_changing_committed_search(self):
        self.batch(0, graph=False)
        for query in ("pum", "PUM", "missing pum"):
            self.assertEqual(len(self.engine.preview(CORPUS, query)["items"]), 1)
        # Trailing whitespace completes the word; only the last partial term expands.
        self.assertEqual(self.engine.preview(CORPUS, "pum ")["items"], [])
        self.assertEqual(self.engine.preview(CORPUS, "pum missing")["items"], [])
        self.assertEqual(self.engine.search(CORPUS, "pum")["items"], [])

    def test_preview_matches_authored_temporal_eligibility_and_modalities(self):
        for index in range(5):
            self.batch(index)
        gold = json.loads(read_text("fixtures", "pump", MANIFEST["gold"]))
        for expected in gold["states"]:
            with self.subTest(expected["id"]):
                result = self.engine.preview(CORPUS, "Pum", mode="graphrag",
                    knowledge_cutoff=expected["knowledge_cutoff"], valid_time=expected["valid_time"])
                self.assertEqual({item["assertion_id"] for item in result["items"]}, set(expected["assertion_ids"]))
                self.assertEqual({item["assertion_id"]: item["modality"] for item in result["items"]}, expected["modalities"])
                self.assertEqual({item["assertion_id"] for item in result["items"] if item["disputed"]}, set(expected["disputed_ids"]))

    def test_snapshot_and_knowledge_scope_never_leak_later_publications(self):
        first = self.batch(0)
        self.batch(1)
        old = self.engine.preview(CORPUS, "Pum", snapshot_id=first["snapshot_id"], mode="graphrag")
        historical = self.engine.preview(CORPUS, "Pum", knowledge_cutoff=first["published_at"], mode="graphrag")
        for result in (old, historical):
            self.assertEqual([item["assertion_id"] for item in result["items"]], ["a-initial"])
        self.assertEqual(old["scope"]["snapshot_id"], first["snapshot_id"])
        self.assertEqual(self.engine.preview(CORPUS, "Pum", knowledge_cutoff="2025-01-05T10:02:00Z")["items"], [])
        with self.assertRaises(DomainError):
            self.engine.preview("different-corpus", "Pum", snapshot_id=first["snapshot_id"])

    def test_source_preview_rejects_world_time_and_graph_without_extraction(self):
        self.batch(0, graph=False)
        for kwargs, code in (({"valid_time": "2025-01-10T00:00:00Z"}, "unsupported_temporal_query"),
                             ({"mode": "graphrag"}, "unsupported_capability")):
            with self.assertRaises(DomainError) as error:
                self.engine.preview(CORPUS, "Pum", **kwargs)
            self.assertEqual(error.exception.code, code)

    def test_fixed_scan_result_and_evidence_limits_report_truncation(self):
        record = json.loads(read_text("fixtures", "pump", "01-initial.jsonl"))
        records = [dict(record, event_id=f"event-{index}", document_id=f"doc-{index}") for index in range(501)]
        job = self.engine.ingest(CORPUS, records, "many-sources")
        self.engine.publish_snapshot(job["job_id"])
        result = self.engine.preview(CORPUS, "Pum")
        self.assertEqual(result["usage"]["scanned"], 501)
        self.assertEqual(len(result["items"]), 12)
        self.assertLessEqual(result["usage"]["evidence_chars"], 14400)
        self.assertTrue(result["truncated"])
        self.assertNotIn("scan_or_time_budget", result["stop_reasons"])
        self.assertIn("candidate_budget", result["stop_reasons"])
        self.assertEqual(result["budget"]["max_request_wall_ms"], 750)
        self.assertEqual(result["budget"]["max_scan"], 20000)
        self.assertEqual(self.engine.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_graph_expands_only_one_hop_over_real_assertions(self):
        record = json.loads(read_text("fixtures", "pump", "01-initial.jsonl"))
        template = json.loads(read_text("fixtures", "pump", "01-initial.assertions.json"))[0]
        pairs = [("Alpha", "Beta"), ("Beta", "Gamma"), ("Gamma", "Delta")]
        spans = [f"{left} links {right}." for left, right in pairs]
        record["text"] = " ".join(spans)
        record["content_sha256"] = record["source_sha256"] = text_hash(record["text"])
        assertions = []
        for index, ((left, right), text) in enumerate(zip(pairs, spans)):
            start = record["text"].index(text)
            assertion = dict(deepcopy(template), assertion_id=f"link-{index}", text=text, start=start, end=start + len(text),
                             subject_id=left.lower(), subject_label=left, object_id=right.lower(), object_label=right)
            assertion.pop("relation_group")
            assertion.pop("qualifiers")
            assertions.append(assertion)
        job = self.engine.ingest(CORPUS, [record], "chain")
        self.engine.stage_assertions(job["job_id"], assertions)
        self.engine.publish_snapshot(job["job_id"])
        result = self.engine.preview(CORPUS, "Alph", mode="graphrag")
        self.assertEqual({item["assertion_id"] for item in result["items"]}, {"link-0", "link-1"})
        expanded = next(item for item in result["items"] if item["assertion_id"] == "link-1")
        self.assertEqual(expanded["selection_reason"], {"channel": "graph_expansion", "predecessor_entity": "beta", "hop": 1})

    def test_deadline_includes_projection_and_recovers_without_writes(self):
        self.batch(0)
        before = tuple(self.engine.db.iterdump())
        clock = [0.0]
        events = self.engine._events

        def exhausted(*args, **kwargs):
            self.assertEqual(self.engine._query_deadline, 0.75)
            clock[0] = 0.8
            return events(*args, **kwargs)

        with patch("graphrag_discovery.engine.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.engine, "_events", side_effect=exhausted):
            with self.assertRaises(DomainError) as error:
                self.engine.preview(CORPUS, "Pum")
        self.assertEqual(error.exception.code, "query_budget_exhausted")
        self.assertEqual(tuple(self.engine.db.iterdump()), before)
        self.assertIsNone(self.engine._query_deadline)
        self.assertTrue(self.engine.preview(CORPUS, "Pum")["items"])

    def test_invalid_queries_and_vector_modes_fail_explicitly(self):
        self.batch(0)
        for query in (None, "", "x", " " * 2, "x" * 257, "a " * 17):
            with self.subTest(query=query), self.assertRaises(DomainError) as error:
                self.engine.preview(CORPUS, query)
            self.assertEqual(error.exception.code, "invalid_query")
        for mode in ("dense", "hybrid"):
            with self.subTest(mode=mode), self.assertRaises(DomainError) as error:
                self.engine.preview(CORPUS, "Pum", mode=mode)
            self.assertEqual(error.exception.code, "unsupported_capability")


if __name__ == "__main__":
    unittest.main()
