"""Tiny independent oracle/runner checks; these are not actual agent trials."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import agent_evaluation as evaluation
from tools import local_agent


CATALOG = {"families": {"noise": ["Noise - Residential", "Noise - Commercial"], "rodent": ["Rodent"]}}


def spec(**changes):
    result = {"operation": "aggregate", "timezone": "America/New_York", "dataset_version": "real-test",
              "time": {"field": "created_date", "gte": "2025-06-01T00:00:00-04:00", "lt": "2025-11-01T00:00:00-04:00"},
              "group_by": [], "metrics": ["count"], "rank_by": "count", "rank_order": "desc", "top_n": 20}
    result.update(changes)
    return result


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source, self.database = self.root / "source.jsonl", self.root / "oracle.sqlite"
        self.rows = [
            {"unique_key": "A", "created_date": "2025-06-01T04:00:00+00:00", "is_closed": True, "closure_hours": 24,
             "complaint_type": "Rodent", "borough": "QUEENS", "agency": "P", "nta2020": "R1", "location": {"lat": 40.72, "lon": -73.95}},
            {"unique_key": "B", "created_date": "2025-06-02T04:00:00+00:00", "is_closed": False,
             "complaint_type": "Rodent", "borough": "QUEENS", "agency": "Q", "nta2020": "R2"},
            {"unique_key": "C", "created_date": "2025-10-01T04:00:00+00:00", "is_closed": True, "closure_hours": 48,
             "complaint_type": "Rodent", "borough": "QUEENS", "agency": "P", "nta2020": "R1", "location": {"lat": 40.72, "lon": -73.95}},
            {"unique_key": "D", "created_date": "2025-10-02T04:00:00+00:00", "is_closed": True, "closure_hours": 72,
             "complaint_type": "Noise - Residential", "agency": "Q", "nta2020": "PARK"},
            {"unique_key": "E", "created_date": "2025-10-03T04:00:00+00:00", "is_closed": True,
             "complaint_type": "Rodent", "borough": "QUEENS", "agency": "Q", "nta2020": "R2"},
        ]
        self.source.write_text("".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")
        self.info = evaluation.build_database(self.source, self.database, min_free_bytes=0)
        self.oracle = evaluation.Oracle(self.database, CATALOG, ["R1", "R2"])

    def tearDown(self):
        self.oracle.close()
        self.tmp.cleanup()

    def test_count_hash_and_source_binding(self):
        result = self.oracle.evaluate(spec())
        expected = hashlib.sha256(b'"A"\n"B"\n"C"\n"D"\n"E"\n').hexdigest()
        self.assertEqual(result["membership"], {"count": 5, "ids_sha256": expected, "geolocated_count": 2})
        self.assertEqual(self.info["source_sha256"], evaluation.sha_file(self.source))
        self.assertEqual(result["rows"], [{"group": {}, "count": 5}])

    def test_no_application_compiler_or_fixture_imports(self):
        source = Path(evaluation.__file__).read_text(encoding="utf-8")
        for name in ("analytics311.compiler", "analytics311.contracts", "analytics311.fixture"):
            self.assertNotIn("from " + name, source)
            self.assertNotIn("import " + name, source)

    def test_counts_mean_percentile_missing_duration(self):
        result = self.oracle.evaluate(spec(metrics=["count", "closed_count", "open_count", "mean_closure_hours", "p90_closure_hours"]))
        self.assertEqual(result["rows"], [{"group": {}, "count": 5, "closed_count": 4, "open_count": 1,
                                           "mean_closure_hours": 48.0, "p90_closure_hours": 67.2}])

    def test_not_null_semantics_and_residential_expansion(self):
        result = self.oracle.evaluate(spec(filters={"not": {"field": "borough", "op": "eq", "value": "QUEENS"}}))
        self.assertEqual(result["membership"]["count"], 1)
        residential = self.oracle.evaluate(spec(filters={"residential_nta": True}))
        self.assertEqual(residential["membership"]["count"], 4)

    def test_geo_radius_bbox_polygon(self):
        for geometry in (
            {"type": "radius", "lat": 40.72, "lon": -73.95, "distance_m": 1},
            {"type": "bbox", "top_left": {"lat": 40.73, "lon": -73.96}, "bottom_right": {"lat": 40.71, "lon": -73.94}},
            {"type": "polygon", "points": [{"lat": 40.72, "lon": -73.95}, {"lat": 40.73, "lon": -73.95}, {"lat": 40.72, "lon": -73.94}]},
        ):
            self.assertEqual(self.oracle.evaluate(spec(geo=geometry))["membership"]["count"], 2)

    def test_histogram_fills_only_covered_buckets(self):
        chosen = spec(time={"field": "created_date", "gte": "2025-06-01T00:00:00-04:00", "lt": "2025-06-04T00:00:00-04:00"},
                      group_by=[{"field": "created_date", "interval": "day"}])
        result = self.oracle.evaluate(chosen)
        self.assertEqual([row["count"] for row in result["rows"]], [1, 1, 0])
        self.assertEqual(result["rows"][-1]["group"]["created_date"], "2025-06-03T00:00:00-04:00")

    def test_comparison_unequal_days_zero_baseline(self):
        chosen = spec(operation="compare_periods", group_by=[{"field": "complaint_type"}], rank_by="rate_change",
                      periods={"baseline": {"gte": "2025-06-01T00:00:00-04:00", "lt": "2025-07-01T00:00:00-04:00"},
                               "current": {"gte": "2025-10-01T00:00:00-04:00", "lt": "2025-11-01T00:00:00-04:00"}})
        chosen.pop("time")
        result = self.oracle.evaluate(chosen)
        new = result["rows"][0]
        self.assertEqual(new["group"], {"complaint_type": "Noise - Residential"})
        self.assertIsNone(new["relative_change"])
        self.assertEqual((new["baseline_days"], new["current_days"]), (30, 31))
        self.assertAlmostEqual(new["rate_change"], 1 / 31)
        self.assertEqual(result["period_membership"]["baseline"]["count"], 2)
        self.assertEqual(result["period_membership"]["current"]["count"], 3)

    def test_injection_fields_rejected_and_values_parameterized(self):
        self.assertEqual(self.oracle.evaluate(spec(filters={"field": "agency", "op": "eq", "value": "P' OR 1=1 --"}))["membership"]["count"], 0)
        with self.assertRaises(ValueError):
            self.oracle.evaluate(spec(filters={"field": "agency;DROP TABLE requests", "op": "eq", "value": "P"}))

    def test_duplicate_source_ids_fail_before_freeze(self):
        bad = self.root / "duplicates.jsonl"
        bad.write_text((json.dumps(self.rows[0]) + "\n") * 2, encoding="utf-8")
        with self.assertRaises(sqlite3.IntegrityError):
            evaluation.build_database(bad, self.root / "duplicate.sqlite", min_free_bytes=0)

    def test_live_result_grade_and_numeric_fabrication(self):
        chosen = spec()
        expected = self.oracle.evaluate(chosen)
        result_id = "a" * 32
        saved = {"result_id": result_id, "spec": chosen, "all_rows": expected["rows"],
                 "rows": expected["rows"], "execution_complete": True, "evidence_level": "elastic_execution",
                 "total": {"value": 5, "relation": "eq"}}
        evaluation.write_new(self.root / (result_id + ".json"), saved)
        class Service:
            runs = self.root
        case = {"expected_status": "answered", "steps": [{"spec": chosen, "expected": expected}]}
        trace = {"status": "finished", "events": [
            {"kind": "tool", "name": "describe_dataset", "arguments": {}, "output": {}},
            {"kind": "tool", "name": "run_analysis", "arguments": {"spec": chosen}, "output": saved}],
            "final": {"status": "answered", "answer": "Five requests.", "result_ids": [result_id],
                      "facts": [{"result_id": result_id, "path": "/total/value", "value": 5}]}}
        self.assertTrue(evaluation.grade_trial(case, trace, Service(), self.oracle)["automatic_pass"])
        trace["final"]["facts"][0]["value"] = 6
        failed = evaluation.grade_trial(case, trace, Service(), self.oracle)
        self.assertFalse(failed["automatic_pass"])
        self.assertIn("fabricated_or_mismatched_numeric_evidence", failed["hard_failures"])

    def test_record_csv_membership_and_duplicate_rejected(self):
        result = self.oracle.evaluate(spec(operation="records"))
        identifier = "b" * 32
        path = self.root / (identifier + ".csv")
        class Service:
            runs = self.root
        for ids, valid in ((["E", "C", "A", "B", "D"], True), (["A", "A", "C", "D", "E"], False)):
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["unique_key"])
                writer.writerows([[value] for value in ids])
            job = {"job_id": identifier, "file": str(path), "status": "complete", "complete": True,
                   "sha256": evaluation.sha_file(path), "rows_written": 5}
            self.assertEqual(evaluation._csv_check(self.oracle, Service(), job, result, "records_csv"), valid)

    def test_wrong_or_empty_preview_fails_despite_exact_total(self):
        chosen = spec(operation="records", preview_limit=2)
        expected = self.oracle.evaluate(chosen)
        self.assertEqual(expected["preview_ids"], ["A", "B"])
        result_id = "c" * 32
        for ids in ([], ["A"], ["C", "D"], ["B", "A"]):
            saved = {"result_id": result_id, "spec": chosen, "all_rows": [{"unique_key": value} for value in ids],
                     "rows": [{"unique_key": value} for value in ids], "execution_complete": True,
                     "evidence_level": "elastic_execution", "total": {"value": 5, "relation": "eq"}}
            (self.root / (result_id + ".json")).write_text(json.dumps(saved), encoding="utf-8")
            trace = {"status": "finished", "events": [
                {"kind": "tool", "name": "describe_dataset", "arguments": {}, "output": {}},
                {"kind": "tool", "name": "run_analysis", "arguments": {"spec": chosen}, "output": saved}],
                "final": {"status": "answered", "answer": "Five requests.", "result_ids": [result_id],
                          "facts": [{"result_id": result_id, "path": "/total/value", "value": 5}]}}
            case = {"expected_status": "answered", "steps": [{"spec": chosen, "expected": expected}]}
            grade = evaluation.grade_trial(case, trace, SimpleNamespace(runs=self.root), self.oracle)
            self.assertFalse(grade["automatic_pass"])
            self.assertFalse(grade["checks"]["step_1_query_and_numbers"])

    def test_two_different_empty_queries_are_not_intent_equivalent(self):
        wanted = spec(operation="records", filters={"field": "unique_key", "op": "eq", "value": "MISSING-A"})
        actual = spec(operation="records", filters={"field": "unique_key", "op": "eq", "value": "MISSING-B"})
        self.assertFalse(evaluation._case_spec_matches(self.oracle, actual, wanted, self.oracle.evaluate(wanted)))


class ProtocolTests(unittest.TestCase):
    def test_40_cases_with_three_chains_and_adversarial_case(self):
        protocol = evaluation.load(evaluation.QUESTIONS)
        self.assertEqual(len(protocol["questions"]), 40)
        self.assertEqual(len({case["id"] for case in protocol["questions"]}), 40)
        self.assertEqual(sum(case["category"] == "chained" for case in protocol["questions"]), 3)
        self.assertEqual(sum("untrusted_note" in case for case in protocol["questions"]), 1)
        self.assertEqual(protocol["repetitions"], 3)

    def test_missing_trials_never_inflate_rate(self):
        protocol = evaluation.load(evaluation.QUESTIONS)
        frozen = {"cases": protocol["questions"], "pass_threshold": .9}
        report = evaluation.summarize(frozen, [{"question_id": "Q01", "repeat": 1, "grade": {"automatic_pass": True}}])
        self.assertEqual(report["automatic_pass_rate"], 1 / 120)
        self.assertEqual(len(report["missing_trials"]), 119)
        self.assertFalse(report["release_verified"])

    def test_all_automatic_passes_still_require_semantic_review(self):
        protocol = evaluation.load(evaluation.QUESTIONS)
        frozen = {"cases": protocol["questions"], "pass_threshold": .9}
        trials = [{"question_id": case["id"], "repeat": repeat, "grade": {"automatic_pass": True}}
                  for case in protocol["questions"] for repeat in (1, 2, 3)]
        report = evaluation.summarize(frozen, trials)
        self.assertTrue(report["automatic_gate_passed"])
        self.assertFalse(report["release_verified"])
        trials.append(trials[0])
        self.assertFalse(evaluation.summarize(frozen, trials)["automatic_gate_passed"])

    def test_loopback_only_and_no_credentials(self):
        for url in ("https://api.openai.com/v1", "http://example.com/v1", "http://127.0.0.1:8080/v1?key=x",
                    "http://secret@127.0.0.1/v1", "http://127.0.0.1/other", "http://127.0.0.1:0/v1"):
            with self.assertRaises(local_agent.AgentFailure):
                local_agent.endpoint_parts(url)
        self.assertEqual(local_agent.endpoint_parts("http://localhost:8080/v1"), ("127.0.0.1", 8080, "/v1"))

    def test_generated_corpus_cannot_pass_real_prepare_by_coverage_flag(self):
        nta = evaluation.load(evaluation.NTA_RECEIPT)
        fake = SimpleNamespace(config={"backend": "elastic"}, manifest={
            "kind": "generated_test_fixture", "immutable": True, "row_count": 2000000,
            "coverage": {"complete": True}, "geography": {"nta_version": nta["sha256"]}})
        with patch("analytics311.service.AnalyticsService", return_value=fake):
            with self.assertRaisesRegex(ValueError, "real_million_corpus_qualification_required"):
                evaluation.prepare("ignored", "not_read", "not_created", "not_created", model="local")

    def test_actual_loop_dispatches_only_model_requested_tools(self):
        class Service:
            def __init__(self):
                self.called = []
            def describe_dataset(self):
                self.called.append("describe_dataset")
                return {"dataset": {"dataset_version": "test"}}
        class Model:
            model = "mock-only-unit-test"
            def __init__(self):
                self.messages = []
            def complete(self, messages, **kwargs):
                self.messages.append(copy.deepcopy(messages))
                if len(self.messages) == 1:
                    message = {"role": "assistant", "tool_calls": [{"id": "call1", "function": {"name": "describe_dataset", "arguments": "{}"}}]}
                else:
                    message = {"role": "assistant", "content": json.dumps({"status": "needs_clarification", "answer": "Which coordinate?", "facts": [], "result_ids": []})}
                return {"choices": [{"message": message}], "usage": {"prompt_tokens": 10}}
        service, model = Service(), Model()
        trace = local_agent.run_trial(service, model, "Nearby?", seed=101, untrusted_note="untrusted fixture")
        self.assertEqual(trace["status"], "finished")
        self.assertEqual(service.called, ["describe_dataset"])
        self.assertEqual(trace["calls"], 1)
        self.assertIn("untrusted fixture", model.messages[-1][-1]["content"])
        self.assertNotIn("expected", model.messages[0][-1]["content"])

    def test_unknown_tool_never_dispatches(self):
        class Model:
            model = "mock-only-unit-test"
            def complete(self, messages, **kwargs):
                return {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "bad", "function": {"name": "delete_index", "arguments": "{}"}}]}}]}
        trace = local_agent.run_trial(object(), Model(), "Drop data", seed=101)
        self.assertEqual(trace["error"]["code"], "unknown_tool")
        self.assertEqual(trace["status"], "failed")

    def test_percentile_tolerance_is_fixed_and_counts_are_exact(self):
        self.assertTrue(evaluation.numeric_equal(104, 100, "p90_closure_hours"))
        self.assertFalse(evaluation.numeric_equal(106, 100, "p90_closure_hours"))
        self.assertFalse(evaluation.numeric_equal(101, 100, "count"))
        self.assertFalse(evaluation.numeric_equal(True, 1, "count"))

    def test_malformed_function_is_a_preserved_trial_failure(self):
        class Model:
            model = "mock-only-unit-test"
            def complete(self, messages, **kwargs):
                return {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "bad", "function": "not-an-object"}]}}]}
        trace = local_agent.run_trial(object(), Model(), "Count", seed=101)
        self.assertEqual(trace["error"]["code"], "malformed_tool_call")
        self.assertEqual(trace["status"], "failed")

    def test_semantic_review_is_hash_bound_and_missing_judgments_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = evaluation.load(evaluation.QUESTIONS)["questions"]
            frozen = {"cases": cases, "pass_threshold": .9, "development_only": False, "minimum_passes_per_question": 1}
            freeze = root / "freeze.json"
            evaluation.write_new(freeze, frozen)
            fingerprint = evaluation.sha_file(freeze)
            directory = root / "trials"
            directory.mkdir()
            # Authored unit-test grading records, not model-trial evidence.
            first = directory / "Q01-r1.json"
            evaluation.write_new(first, {"question_id": "Q01", "repeat": 1, "freeze_sha256": fingerprint,
                                         "grade": {"automatic_pass": True}})
            judgments = {"freeze_sha256": fingerprint,
                         "reviewer": {"id": "unit-test-reviewer", "kind": "independent_ai_session", "was_answering_agent": False},
                         "reviews": [{"question_id": "Q01", "repeat": 1, "trial_sha256": evaluation.sha_file(first),
                                      "notes": "Authored unit-test judgments only.", "checks": {key: True for key in evaluation.REVIEW_CHECKS}}]}
            reviews = root / "reviews.json"
            evaluation.write_new(reviews, judgments)
            report = evaluation.review(freeze, [directory], reviews, root / "graded.json")
            self.assertEqual(report["end_to_end_pass_rate"], 1 / 120)
            self.assertFalse(report["agent_quality_gate_passed"])
            judgments["reviews"][0]["trial_sha256"] = "0" * 64
            reviews.write_text(json.dumps(judgments), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review_does_not_match_exact_trial"):
                evaluation.review(freeze, [directory], reviews, root / "bad.json")

    def test_repetition_and_resume_preserve_failed_trials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "oracle.sqlite"
            db = evaluation.connect(database, readonly=False)
            db.close()
            cases = [{"id": f"Q{number:02}", "question": f"Clarify {number}", "expected_status": "needs_clarification", "steps": []}
                     for number in range(1, 41)]
            manifest = {"dataset_version": "mock-unit-only"}
            fake = SimpleNamespace(manifest=manifest, catalog=CATALOG)
            frozen = {"cases": cases, "pass_threshold": .9, "development_only": True,
                      "code_sha256": evaluation.code_hashes(), "questions_sha256": evaluation.sha_file(evaluation.QUESTIONS),
                      "database_sha256": evaluation.sha_file(database), "manifest_sha256": evaluation.digest(manifest),
                      "catalog_sha256": evaluation.digest(CATALOG), "model": "mock-unit-only",
                      "residential_nta_codes": [], "model_settings": {"seeds": [101, 202, 303]}}
            freeze = root / "freeze.json"
            evaluation.write_new(freeze, frozen)
            output = root / "run"
            calls = []
            def failed_trial(service, model, question, *, seed, **kwargs):
                calls.append((question, seed))
                return {"status": "failed", "question": question, "seed": seed, "model": "mock-unit-only",
                        "events": [], "final": None, "elapsed_seconds": .01, "error": {"code": "mock_failure"}}
            with patch("analytics311.service.AnalyticsService", return_value=fake), patch.object(evaluation, "LocalModel") as model, patch.object(evaluation, "run_trial", side_effect=failed_trial):
                model.return_value.identify.return_value = {"model_id": "mock-unit-only"}
                first = evaluation.run("unused", freeze, database, output, endpoint="http://127.0.0.1:8080/v1", repetition=2)
                self.assertEqual(len(calls), 40)
                self.assertTrue(first["execution_complete"])
                self.assertEqual(first["attempted_trials"], 40)
                trial_hash = evaluation.sha_file(output / "Q01-r2.json")
                second = evaluation.run("unused", freeze, database, output, endpoint="http://127.0.0.1:8080/v1", repetition=2, resume=True)
                self.assertEqual(len(calls), 40)
                self.assertEqual(second["automatic_passes"], 0)
                evaluation.run("unused", freeze, database, output, endpoint="http://127.0.0.1:8080/v1", repetition=1, resume=True)
                self.assertEqual(len(calls), 80)
                self.assertEqual(evaluation.sha_file(output / "Q01-r2.json"), trial_hash)
                with self.assertRaisesRegex(ValueError, "resume_identity_changed"):
                    evaluation.run("unused", freeze, database, output, endpoint="http://127.0.0.1:8080/v1", repetition=3, resume=True, seconds=120)


if __name__ == "__main__":
    unittest.main()
