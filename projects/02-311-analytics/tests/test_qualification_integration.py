"""Observed scope crosses capture/normalization/service/CLI without becoming population coverage."""
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from analytics311.capture import FIELD_TYPES, capture_window
from analytics311.cli import main
from analytics311.errors import AnalyticsError
from analytics311.qualification import SCOPE, comparison_qualification
from analytics311.service import AnalyticsService, file_hash
from analytics311.workloads import normalize_file


class AuthoredSource:
    def __init__(self, dates=None):
        self.rows = [{"unique_key": str(i + 1), "created_date": date, "complaint_type": "Rodent",
                      "borough": "BROOKLYN", "status": "Open", "agency": "DOHMH",
                      "source_row_id": f"row-{i}", "source_updated_at": "2026-10-07T01:00:00Z"}
                     for i, date in enumerate(dates or ["2025-04-10T12:00:00", "2025-05-10T12:00:00", "2025-05-11T12:00:00"])]

    def get_json(self, path, params=None, **kwargs):
        if path.startswith("/api/views"):
            return {"id": "erm2-nwe9", "rowsUpdatedAt": 123, "viewLastModified": 456,
                    "columns": [{"fieldName": field, "dataTypeName": kind} for field, kind in FIELD_TYPES.items()]}, {}
        headers = {key: "Wed, 07 Oct 2026 02:00:00 GMT" for key in ("x-soda2-truth-last-modified", "x-soda2-secondary-last-modified")}
        if params["$select"].startswith("count("):
            return [{"row_count": str(len(self.rows)), "unique_count": str(len(self.rows)),
                     "max_updated_at": "2026-10-07T01:00:00Z"}], headers
        match = re.search(r"unique_key > '([^']+)'", params["$where"])
        cursor = match[1] if match else ""
        return [row.copy() for row in self.rows if row["unique_key"] > cursor][:params["$limit"]], headers


class QualificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw = self.root / "raw.jsonl"
        self.normalized = self.root / "normalized.jsonl"
        capture_window("2025-04-01", "2025-06-01", self.raw, client=AuthoredSource(), page_size=2, min_free_bytes=0)
        normalize_file(self.raw, self.normalized, min_free_bytes=0)
        self.manifest = json.loads(self.normalized.with_suffix(".manifest.json").read_text())
        (self.root / "catalog.json").write_text("{}")
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps({"backend": "fixture", "fixture_path": "normalized.jsonl",
            "manifest_path": "normalized.manifest.json", "catalog_path": "catalog.json", "runs_dir": "runs", "export_inline": True}))
        self.service = AnalyticsService(self.profile)
        self.elastic_profile = self.root / "elastic.json"
        self.elastic_profile.write_text(json.dumps({"backend": "elastic", "elastic_url": "http://127.0.0.1:9200",
            "allow_insecure_local": True, "index": "integration-v1", "manifest_path": "frozen.json"}))

    def request(self, **changes):
        return {"dataset_version": self.manifest["dataset_version"], "operation": "records",
                "as_of": "2026-10-07T12:00:00Z", "timezone": "America/New_York",
                "time": {"gte": "2025-04-01T00:00:00-04:00", "lt": "2025-06-01T00:00:00-04:00"}, **changes}

    def comparison(self):
        value = self.request(operation="compare_periods", group_by=[{"field": "agency"}],
            periods={"baseline": {"gte": "2025-04-01T00:00:00-04:00", "lt": "2025-05-01T00:00:00-04:00"},
                     "current": {"gte": "2025-05-01T00:00:00-04:00", "lt": "2025-06-01T00:00:00-04:00"}})
        value.pop("time")
        return value

    def invoke(self, source=None, *extras):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(["--config", str(self.elastic_profile), "ingest", str(source or self.normalized),
                           "--normalized-input", "--freeze", "--coverage-start", "2025-04-01T00:00:00-04:00",
                           "--coverage-end", "2025-06-01T00:00:00-04:00", *extras])
        return result, json.loads(err.getvalue()) if err.getvalue() else None

    def test_capture_normalization_and_service_preserve_observed_scope_and_real_hash_chain(self):
        certificate = comparison_qualification(self.manifest)
        self.assertEqual(certificate["capture_sha256"], file_hash(self.raw))
        self.assertEqual(certificate["normalized_sha256"], file_hash(self.normalized))
        self.assertEqual(certificate["row_count"], 3)
        result = self.service.run_analysis(self.comparison())
        self.assertEqual(result["comparison_scope"], SCOPE)
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["rows"][0]["baseline_count"], 1)
        self.assertEqual(result["rows"][0]["current_count"], 2)
        self.assertTrue(any("not proof" in item for item in result["warnings"]))

    def test_period_outside_capture_and_closure_calendar_cannot_use_creation_qualification(self):
        spec = self.comparison()
        spec["periods"]["current"]["lt"] = "2025-07-01T00:00:00-04:00"
        for value in (spec, self.request(operation="aggregate", group_by=[{"field": "closed_date", "interval": "day"}],
                     time={"field": "closed_date", "gte": "2025-04-01T00:00:00-04:00", "lt": "2025-06-01T00:00:00-04:00"})):
            with self.subTest(spec=value), self.assertRaises(AnalyticsError) as caught:
                self.service.validate_analysis(value)
            self.assertEqual(caught.exception.code, "coverage_gap")

    def test_outside_records_and_closure_records_do_not_claim_observed_scope(self):
        for value in (self.request(time={"gte": "2025-03-01T00:00:00-05:00", "lt": "2025-04-01T00:00:00-04:00"}),
                      self.request(time={"field": "closed_date", "gte": "2025-04-01T00:00:00-04:00", "lt": "2025-06-01T00:00:00-04:00"})):
            with self.subTest(spec=value):
                validated = self.service.validate_analysis(value)
                self.assertEqual(validated["comparison_scope"], "unqualified_snapshot")
                self.assertFalse(validated["coverage_complete"])

    def test_nested_date_filters_without_enclosing_creation_bounds_are_unqualified(self):
        spec = self.request(filters={"any": [{"field": "created_date", "op": "range", "value": {"gte": "2025-03-01T00:00:00Z"}},
                                             {"field": "agency", "op": "eq", "value": "DOHMH"}]})
        spec.pop("time")
        validated = self.service.validate_analysis(spec)
        self.assertEqual(validated["comparison_scope"], "unqualified_snapshot")

    def test_ambiguous_capture_normalizes_but_does_not_qualify(self):
        raw = self.root / "ambiguous.jsonl"
        capture_window("2025-11-01", "2025-11-03", raw, client=AuthoredSource(["2025-11-02T01:30:00"]), min_free_bytes=0)
        result = normalize_file(raw, self.root / "ambiguous-normalized.jsonl", min_free_bytes=0)
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["quality_counts"]["ambiguous_created_date"], 1)
        self.assertNotIn("comparison_qualification", result)
        self.assertEqual(result["comparison_qualification_error"]["code"], "qualification_failed")

    def test_cli_sample_count_mismatch_rejected_before_freeze(self):
        sample = self.root / "sample.jsonl"
        sample.write_text('{"unique_key":"1"}\n')
        sample.with_suffix(".manifest.json").write_text(json.dumps({"sha256": file_hash(sample), "kind": "public_sample",
                                                                  "row_count": 2, "coverage": {"complete": False}}))
        with patch("analytics311.elastic.ElasticClient"), \
             patch("analytics311.ingest._ingest_jsonl_unlocked", return_value={"source_sha256": file_hash(sample), "processed_rows": 1}), \
             patch("analytics311.ingest.freeze_index") as freeze:
            code, error = self.invoke(sample)
        self.assertEqual(code, 2)
        self.assertEqual(error["error"]["code"], "source_count_mismatch")
        freeze.assert_not_called()
        self.assertFalse((self.root / "frozen.json").exists())

    def test_cli_reconciles_and_binds_frozen_index_without_complete_coverage_override(self):
        output = {"source_sha256": self.manifest["sha256"], "processed_rows": 3, "complete": True,
                  "normalized_input": True, "quarantined": False, "index": "integration-v1", "index_uuid": "uuid-test", "quality_counts": {}}
        snapshot = {"index": "integration-v1", "index_uuid": "uuid-test", "row_count": 3, "immutable": True}
        with patch("analytics311.elastic.ElasticClient"), patch("analytics311.ingest._ingest_jsonl_unlocked", return_value=output), \
             patch("analytics311.ingest.freeze_index", return_value=snapshot) as freeze:
            code, error = self.invoke()
        self.assertEqual((code, error), (0, None))
        self.assertEqual(freeze.call_args.kwargs["expected_count"], 3)
        manifest = json.loads((self.root / "frozen.json").read_text())
        self.assertFalse(manifest["coverage"]["complete"])
        self.assertEqual(comparison_qualification(manifest)["index_uuid"], "uuid-test")

    def test_cli_rejects_changed_certificate_before_any_network_or_mutation(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["comparison_qualification"]["population_complete"] = True
        self.normalized.with_suffix(".manifest.json").write_text(json.dumps(manifest))
        with patch("analytics311.elastic.ElasticClient") as client, patch("analytics311.ingest.create_index") as create:
            code, _ = self.invoke(None, "--create-index")
        self.assertEqual(code, 2)
        client.assert_not_called()
        create.assert_not_called()

    def test_cli_rejects_outside_freeze_window_before_any_network_or_mutation(self):
        with patch("analytics311.elastic.ElasticClient") as client, patch("analytics311.ingest.create_index") as create:
            code, _ = self.invoke(None, "--create-index", "--coverage-end", "2025-07-01T00:00:00-04:00")
        self.assertEqual(code, 2)
        client.assert_not_called()
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
