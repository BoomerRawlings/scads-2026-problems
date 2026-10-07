"""Temporal projections checked against independent, authored pump gold."""

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
GOLD = json.loads((FIXTURE_ROOT / MANIFEST["gold"]).read_text(encoding="utf-8"))
CORPUS = MANIFEST["corpus_id"]


def read_batch(index):
    batch = MANIFEST["batches"][index]
    records = [json.loads(line) for line in (FIXTURE_ROOT / batch["records"]).read_text(encoding="utf-8").splitlines()]
    assertions = json.loads((FIXTURE_ROOT / batch["assertions"]).read_text(encoding="utf-8"))
    return batch, records, assertions


def assertion_ids(items):
    return {item["assertion_id"] for item in items if item.get("assertion_id")}


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.time = "2025-01-05T10:00:00Z"
        self.engine = Engine(Path(self.directory.name) / "temporal.sqlite3",
                             clock=lambda: datetime.fromisoformat(self.time.replace("Z", "+00:00")))
        self.addCleanup(self.engine.close)
        self.snapshots = {}

    def publish_batch(self, index, *, assertions_override=None):
        batch, records, assertions = read_batch(index)
        self.time = batch["ingested_at"]
        job = self.engine.ingest(CORPUS, records, idempotency_key=batch["id"])
        self.time = batch["prepared_at"]
        self.engine.stage_assertions(job["job_id"], assertions if assertions_override is None else assertions_override)
        self.time = batch["published_at"]
        snapshot = self.engine.publish_snapshot(job["job_id"], label=batch["id"])
        self.snapshots[batch["id"]] = snapshot["snapshot_id"]
        return snapshot

    def build_history(self, count=5):
        for index in range(count):
            self.publish_batch(index)

    def test_historical_states_match_independent_gold(self):
        """A07–A12: late corrections, plans, conflict, withdrawal, boundaries."""
        self.build_history()
        for expected in GOLD["states"]:
            with self.subTest(expected["id"]):
                run = self.engine.search(CORPUS, GOLD["query"], mode="graphrag",
                                         knowledge_cutoff=expected["knowledge_cutoff"],
                                         valid_time=expected["valid_time"])
                self.assertFalse(run["truncated"])
                self.assertEqual(assertion_ids(run["items"]), set(expected["assertion_ids"]))
                modalities = {item["assertion_id"]: item["modality"] for item in run["items"]}
                self.assertEqual(modalities, expected["modalities"])
                disputed = {item["assertion_id"] for item in run["items"] if item["disputed"]}
                self.assertEqual(disputed, set(expected["disputed_ids"]))

    def test_later_source_and_assertion_are_inaccessible_at_earlier_cutoff(self):
        self.build_history()
        latest = self.snapshots["05-withdrawn"]
        for history in (False, True):
            with self.subTest(history=history), self.assertRaises(DomainError):
                self.engine.get_evidence(CORPUS, latest, assertion_id="b-corrected",
                                         knowledge_cutoff="2025-02-05T00:00:00Z", history=history)
        source = self.engine.search(CORPUS, "Correction", knowledge_cutoff="2025-02-05T00:00:00Z")
        self.assertEqual(source["items"], [])

    def test_future_validity_preserves_planned_modality(self):
        self.build_history(2)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag", valid_time="2025-03-01T00:00:00Z")
        self.assertEqual(assertion_ids(run["items"]), {"b-planned"})
        self.assertEqual(run["items"][0]["modality"], "planned")

    def test_delayed_extraction_becomes_visible_only_at_activation(self):
        """A07/A31: source visibility and interpretation visibility differ."""
        _, records, assertions = read_batch(0)
        job = self.engine.ingest(CORPUS, records, idempotency_key="source-first")
        self.time = "2025-01-05T10:05:00Z"
        self.engine.publish_snapshot(job["job_id"])
        self.time = "2025-01-06T10:00:00Z"
        graph_job = self.engine.ingest(CORPUS, records, idempotency_key="later-extraction")
        self.time = "2025-01-06T10:01:00Z"
        self.engine.stage_assertions(graph_job["job_id"], assertions)
        self.time = "2025-01-06T10:05:00Z"
        self.engine.publish_snapshot(graph_job["job_id"])
        earlier = "2025-01-06T10:02:00Z"
        graph = self.engine.search(CORPUS, "Pump P", mode="graphrag", knowledge_cutoff=earlier)
        text = self.engine.search(CORPUS, "Pump P", knowledge_cutoff=earlier)
        self.assertEqual(graph["items"], [])
        self.assertEqual(len(text["items"]), 1)
        current = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        self.assertEqual(assertion_ids(current["items"]), {"a-initial"})
        self.assertEqual(datetime.fromisoformat(current["items"][0]["recorded_at"]),
                         datetime.fromisoformat("2025-01-06T10:05:00+00:00"))

    def test_current_withdrawal_preserves_history_and_other_support(self):
        self.build_history()
        with self.assertRaises(DomainError):
            self.engine.get_evidence(CORPUS, assertion_id="c-report")
        historical = self.engine.get_evidence(CORPUS, assertion_id="c-report", history=True)
        self.assertEqual(historical["source_status"], "withdrawn")
        self.assertIn("Operator C", historical["text"])
        current = self.engine.get_evidence(CORPUS, assertion_id="b-corrected")
        self.assertEqual(current["source_status"], "active")
        self.assertEqual(current["modality"], "reported")

    def test_old_snapshot_and_superseded_source_are_still_inspectable(self):
        self.build_history()
        old = self.engine.get_evidence(CORPUS, self.snapshots["02-planned"], assertion_id="b-planned")
        self.assertEqual(old["modality"], "planned")
        self.assertEqual(old["source_status"], "active")
        with self.assertRaises(DomainError):
            self.engine.get_evidence(CORPUS, assertion_id="a-initial")
        initial = self.engine.get_evidence(CORPUS, assertion_id="a-initial", history=True)
        self.assertEqual(initial["source_status"], "superseded")
        self.assertEqual(initial["text"], read_batch(0)[2][0]["text"])

    def test_unknown_temporal_endpoint_cannot_silently_become_open(self):
        assertions = read_batch(0)[2]
        assertions[0]["temporal_status"]["to"] = "unknown"
        self.publish_batch(0, assertions_override=assertions)
        untimed = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        timed = self.engine.search(CORPUS, "Pump P", mode="graphrag", valid_time="2025-01-10T00:00:00Z")
        self.assertEqual(assertion_ids(untimed["items"]), {"a-initial"})
        self.assertEqual(timed["items"], [])

    def test_shared_relation_group_alone_does_not_establish_exclusivity(self):
        self.build_history(3)
        assertions = read_batch(3)[2]
        assertions[0]["qualifiers"] = {"exclusive": False}
        self.publish_batch(3, assertions_override=assertions)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag", valid_time="2025-02-04T00:00:00Z")
        self.assertEqual(assertion_ids(run["items"]), {"b-corrected", "c-report"})
        self.assertFalse(any(item["disputed"] for item in run["items"]))

    def test_every_historical_assertion_opens_exact_expected_span_and_hash(self):
        self.build_history()
        for index in range(len(MANIFEST["batches"])):
            for assertion in read_batch(index)[2]:
                with self.subTest(assertion["assertion_id"]):
                    evidence = self.engine.get_evidence(CORPUS, assertion_id=assertion["assertion_id"], history=True)
                    self.assertEqual(evidence["text"], assertion["text"])
                    self.assertEqual(evidence["start"], assertion["start"])
                    self.assertEqual(evidence["end"], assertion["end"])
                    self.assertEqual(evidence["text_hash"], hashlib.sha256(assertion["text"].encode("utf-8")).hexdigest())

    def test_world_state_changes_without_new_commit_match_gold(self):
        """A26: one snapshot and K can still support different V0/V1 states."""
        self.build_history()
        for expected in GOLD["world_state_comparisons"]:
            with self.subTest(expected["id"]):
                snapshot = self.snapshots[expected["analysis_batch"]]
                run = self.engine.search(CORPUS, "Pump P", snapshot_id=snapshot, mode="graphrag")
                baseline = self.engine.save_baseline(run["run_id"], kind="entity_neighborhood",
                                                     seed_entity_ids=["pump-p"], hops=1)
                comparison = self.engine.compare(baseline["baseline_id"], target_snapshot_id=snapshot,
                                                 mode="world_state_change",
                                                 knowledge_cutoff=expected["knowledge_cutoff"],
                                                 valid_from_time=expected["valid_from_time"],
                                                 valid_to_time=expected["valid_to_time"])
                self.assertFalse(comparison["truncated"])
                before = [item for change in comparison["changes"] for item in change["before"]]
                after = [item for change in comparison["changes"] for item in change["after"]]
                self.assertEqual(assertion_ids(before), set(expected["before_assertion_ids"]))
                self.assertEqual(assertion_ids(after), set(expected["after_assertion_ids"]))
                self.assertEqual({item["modality"] for item in after}, {expected["after_modality"]})

    def test_correction_comparison_pairs_old_and_new_evidence(self):
        self.build_history(2)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        baseline = self.engine.save_baseline(run["run_id"])
        self.publish_batch(2)
        result = self.engine.compare(baseline["baseline_id"])
        corrections = [change for change in result["changes"] if "correction" in change["categories"]]
        self.assertEqual(len(corrections), 2)
        self.assertEqual(assertion_ids([item for change in corrections for item in change["before"]]),
                         {"a-planned", "b-planned"})
        self.assertEqual(assertion_ids([item for change in corrections for item in change["after"]]),
                         {"a-corrected", "b-corrected"})
        self.assertFalse(result["truncated"])

    def test_baseline_kinds_distinguish_new_neighbor_from_saved_lineages(self):
        """A28: identical canvas/results do not make the two scopes equal."""
        self.build_history(3)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        saved = self.engine.save_baseline(run["run_id"], kind="saved_findings")
        neighborhood = self.engine.save_baseline(run["run_id"], kind="entity_neighborhood",
                                                seed_entity_ids=["pump-p"])
        self.publish_batch(3)
        saved_result = self.engine.compare(saved["baseline_id"])
        neighborhood_result = self.engine.compare(neighborhood["baseline_id"])
        saved_new = assertion_ids([item for change in saved_result["changes"] for item in change["after"]])
        neighborhood_new = assertion_ids([item for change in neighborhood_result["changes"] for item in change["after"]])
        self.assertNotIn("c-report", saved_new)
        self.assertIn("c-report", neighborhood_new)

    def test_ranking_disappearance_does_not_remove_saved_supported_finding(self):
        """A20: compare the evidence scope, not independently ranked top-k."""
        self.build_history(1)
        old_run = self.engine.search(CORPUS, "Pump P", mode="graphrag", limit=1)
        baseline = self.engine.save_baseline(old_run["run_id"])
        _, records, assertions = read_batch(0)
        record, assertion = deepcopy(records[0]), deepcopy(assertions[0])
        text = "Operator D inspected Pump P; Pump P was inspected by Operator D."
        record.update(event_id="inspection-v1", document_id="inspection", text=text,
                      source_uri="fixture://pump/inspection", source_available_at="2025-01-06T09:00:00Z")
        record["source_sha256"] = record["content_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        assertion.update(assertion_id="inspection-claim", document_id="inspection",
                         subject_id="operator-d", subject_label="Operator D", text=text,
                         start=0, end=len(text), relation_group="pump-inspection", qualifiers={})
        self.time = "2025-01-06T10:00:00Z"
        job = self.engine.ingest(CORPUS, [record], idempotency_key="ranking-distraction")
        self.engine.stage_assertions(job["job_id"], [assertion])
        self.engine.publish_snapshot(job["job_id"])
        new_run = self.engine.search(CORPUS, "Pump P", mode="graphrag", limit=1)
        self.assertEqual(assertion_ids(new_run["items"]), {"inspection-claim"})
        result = self.engine.compare(baseline["baseline_id"])
        self.assertIn("a-initial", assertion_ids(result["unchanged"]))
        self.assertFalse(any("retraction" in change["categories"] for change in result["changes"]))

    def test_withdrawal_comparison_does_not_invent_a_world_transition(self):
        self.build_history(4)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag", valid_time="2025-02-04T00:00:00Z")
        baseline = self.engine.save_baseline(run["run_id"], kind="entity_neighborhood", seed_entity_ids=["pump-p"])
        self.publish_batch(4)
        comparison = self.engine.compare(baseline["baseline_id"])
        retractions = [change for change in comparison["changes"] if "retraction" in change["categories"]]
        self.assertEqual(assertion_ids([item for change in retractions for item in change["before"]]), {"c-report"})
        self.assertTrue(all(not change["after"] for change in retractions))
        self.assertFalse(any("world_state_change" in change["categories"] for change in comparison["changes"]))

    def test_world_state_comparison_respects_zero_scan_budget(self):
        self.build_history(3)
        run = self.engine.search(CORPUS, "Pump P", mode="graphrag")
        baseline = self.engine.save_baseline(run["run_id"], kind="entity_neighborhood", seed_entity_ids=["pump-p"])
        comparison = self.engine.compare(baseline["baseline_id"], mode="world_state_change",
                                         valid_from_time="2025-01-31T00:00:00Z",
                                         valid_to_time="2025-02-04T00:00:00Z", budget={"max_scan": 0})
        self.assertTrue(comparison["truncated"])
        self.assertFalse(comparison["coverage"]["complete_within_candidate_scope"])
        self.assertEqual(comparison["changes"], [])


if __name__ == "__main__":
    unittest.main()
