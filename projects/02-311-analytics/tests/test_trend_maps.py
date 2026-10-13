"""Mocked publication contracts; no claim of live Kibana map parity."""

import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.service import AnalyticsService
from analytics311.qualification import SCOPE, qualify_frozen_index
from analytics311.trend_maps import RESULT_MAPPING, publish_trend_map
from tests.test_qualification import frozen


RESULT_INDEX = "analytics311-results-v1"


class FakeArtifactClient:
    def __init__(self):
        self.calls = []
        self.documents = {}
        self.mapping = copy.deepcopy(RESULT_MAPPING)
        self.alias = False
        self.fail_status = None
        self.truncate_bulk = False
        self.pipeline_changes_document = False

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/_mapping"):
            return {"wrong-concrete-v1" if self.alias else RESULT_INDEX: copy.deepcopy(self.mapping)}
        if "_bulk" in path:
            lines = [json.loads(line) for line in body.splitlines()]
            items = []
            for action, document in zip(lines[::2], lines[1::2]):
                identifier = action["create"]["_id"]
                if self.fail_status:
                    status = self.fail_status
                elif identifier in self.documents:
                    status = 409
                else:
                    status = 201
                    self.documents[identifier] = document
                    if self.pipeline_changes_document:
                        self.documents[identifier]["current_count"] = 999
                items.append({"create": {"_id": identifier, "_index": RESULT_INDEX, "status": status, "_shards": {"failed": 0}}})
            return {"errors": any(item["create"]["status"] != 201 for item in items), "items": items[:-1] if self.truncate_bulk else items}
        if path.endswith("/_mget"):
            return {"docs": [{"_id": identifier, "_index": RESULT_INDEX, "found": True, "_source": self.documents[identifier]} for identifier in body["ids"]]}
        raise AssertionError(f"Unexpected artifact API path: {path}")


def row(nta, baseline, current, group_id):
    return {"group": {"nta2020": nta}, "group_id": group_id, "count": current,
            "baseline_count": baseline, "current_count": current, "absolute_change": current - baseline,
            "relative_change": (current - baseline) / baseline if baseline else None,
            "rate_change": current / 31 - baseline / 30}


class TrendMapTests(unittest.TestCase):
    def setUp(self):
        self.service = SimpleNamespace(
            config={"backend": "elastic", "index": "nyc311-demo-v1", "elastic_url": "https://localhost:9200",
                    "kibana": {"result_index": RESULT_INDEX, "trend_map_id": "nta-trend-map", "trend_data_view_id": "trend-data-view", "trend_metric": "relative_change"}},
            budgets={"max_map_groups": 1000, "deadline_seconds": 30},
            manifest={"index": "nyc311-demo-v1", "geography": {"nta_version": "NTA2020-pinned-test"},
                      "coverage": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2026-01-01T00:00:00-05:00", "complete": True}},
        )
        self.saved = {
            "result_id": "a" * 32, "created_at": "2026-01-02T12:00:00Z", "execution_complete": True, "coverage_complete": True,
            "spec": {"operation": "compare_periods", "dataset_version": "real-snapshot-v1", "group_by": [{"field": "nta2020"}],
                     "periods": {"baseline": {"gte": "2025-11-01T00:00:00-04:00", "lt": "2025-12-01T00:00:00-05:00"},
                                 "current": {"gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"}}},
            "all_rows": [row("BK0101", 2, 4, "bk"), row("QN0101", 0, 3, "qn"), row(None, 1, 2, "unknown")],
        }
        self.service._coverage = lambda spec: AnalyticsService._coverage(self.service, spec)
        self.client = FakeArtifactClient()
        self.mock_client = patch("analytics311.trend_maps.ElasticClient", return_value=self.client).start()
        self.addCleanup(patch.stopall)

    def assert_error(self, code, selected=None):
        with self.assertRaises(AnalyticsError) as caught:
            publish_trend_map(self.service, self.saved, selected)
        self.assertEqual(caught.exception.code, code)

    def test_publish_dedicated_result_documents_and_locator(self):
        result = publish_trend_map(self.service, self.saved, None)
        self.assertEqual((result["mapped_group_count"], result["excluded_group_count"]), (2, 1))
        self.assertFalse(result["parity_verified"])
        self.assertEqual(len(self.client.documents), 2)
        docs = {document["nta2020"]: document for document in self.client.documents.values()}
        self.assertEqual((docs["BK0101"]["baseline_count"], docs["BK0101"]["current_count"], docs["BK0101"]["relative_change"]), (2, 4, 1))
        self.assertIsNone(docs["QN0101"]["relative_change"])
        self.assertEqual(docs["BK0101"]["created_at"], self.saved["created_at"])
        self.assertEqual(result["locator_request"]["params"]["filters"][0]["query"], {"term": {"result_id": "a" * 32}})
        self.assertEqual(result["source_periods"], self.saved["spec"]["periods"])
        self.assertNotIn("created_date", json.dumps(result["locator_request"]))
        self.assertEqual(self.mock_client.call_args.kwargs["api_key_env"], "ELASTIC_ARTIFACT_API_KEY")
        self.assertTrue(all("nyc311-demo-v1" not in path for _, path, _ in self.client.calls))

    def test_replay_conflicts_verify_identical_documents(self):
        first = publish_trend_map(self.service, self.saved, None)
        original = copy.deepcopy(self.client.documents)
        second = publish_trend_map(self.service, self.saved, None)
        self.assertEqual(first, second)
        self.assertEqual(original, self.client.documents)
        self.assertTrue(any(path.endswith("/_mget") for _, path, _ in self.client.calls))

    def test_conflicting_document_is_never_overwritten(self):
        publish_trend_map(self.service, self.saved, None)
        identifier = next(iter(self.client.documents))
        self.client.documents[identifier]["current_count"] = 999
        self.assert_error("partial_execution")
        self.assertEqual(self.client.documents[identifier]["current_count"], 999)

    def test_ingest_pipeline_cannot_silently_change_published_metrics(self):
        self.client.pipeline_changes_document = True
        self.assert_error("partial_execution")

    def test_selected_map_stays_scoped_after_all_groups_published(self):
        selected = [self.saved["all_rows"][0]]
        result = publish_trend_map(self.service, self.saved, selected)
        publish_trend_map(self.service, self.saved, None)
        self.assertEqual(result["selected_nta_ids"], ["BK0101"])
        self.assertEqual(result["group_ids"], ["bk"])
        self.assertEqual(result["locator_request"]["params"]["filters"][0]["query"],
                         {"bool": {"filter": [{"term": {"result_id": "a" * 32}}, {"terms": {"nta2020": ["BK0101"]}}]}})
        self.assertEqual(len(self.client.documents), 2)

    def test_null_only_selection_matches_none(self):
        result = publish_trend_map(self.service, self.saved, [self.saved["all_rows"][-1]])
        self.assertEqual(result["mapped_group_count"], 0)
        self.assertEqual(result["excluded_group_count"], 1)
        self.assertEqual(self.client.documents, {})
        self.assertEqual(result["locator_request"]["params"]["filters"][0]["query"]["bool"]["filter"][-1], {"match_none": {}})

    def test_setup_and_source_protection_fail_before_writes(self):
        self.service.config["kibana"]["result_index"] = "nyc311-demo-v1"
        self.assert_error("invalid_configuration")
        self.assertEqual(self.client.calls, [])
        self.service.config["kibana"]["result_index"] = RESULT_INDEX
        self.service.manifest["geography"] = {}
        self.assert_error("unsupported_operation")
        self.assertEqual(self.client.calls, [])

    def test_fixture_wrong_dimensions_and_incomplete_execution_rejected(self):
        self.service.config["backend"] = "fixture"
        self.assert_error("unsupported_operation")
        self.service.config["backend"] = "elastic"
        self.saved["spec"]["group_by"] = [{"field": "borough"}]
        self.assert_error("unsupported_operation")
        self.saved["spec"]["group_by"] = [{"field": "nta2020"}]
        self.saved["coverage_complete"] = False
        self.assert_error("coverage_gap")
        self.assertEqual(self.client.calls, [])

    def test_alias_or_unmarked_mapping_rejected(self):
        self.client.alias = True
        self.assert_error("invalid_configuration")
        self.client.alias = False
        self.client.mapping["mappings"]["_meta"] = {}
        self.assert_error("invalid_configuration")
        self.assertEqual(self.client.documents, {})

    def test_budget_checked_before_publishing_and_batches_are_bounded(self):
        self.service.budgets["max_map_groups"] = 2
        self.assert_error("budget_exceeded")
        self.assertEqual(self.client.calls, [])
        self.service.budgets["max_map_groups"] = 1000
        self.saved["all_rows"] = [row(f"NTA-{i}", 1, 2, f"group-{i}") for i in range(501)]
        result = publish_trend_map(self.service, self.saved, None)
        sizes = [len(body.splitlines()) // 2 for _, path, body in self.client.calls if "_bulk" in path]
        self.assertEqual(sizes, [500, 1])
        self.assertEqual(result["published_group_count"], 501)

    def test_partial_bulk_and_failed_item_return_no_locator(self):
        self.client.truncate_bulk = True
        self.assert_error("partial_execution")
        self.client.truncate_bulk = False
        self.client.fail_status = 429
        self.assert_error("partial_execution")

    def test_selection_must_match_saved_groups(self):
        modified = copy.deepcopy(self.saved["all_rows"][0])
        modified["current_count"] = 9000
        self.assert_error("invalid_spec", [modified])
        self.assertEqual(self.client.calls, [])

    def observed_snapshot(self):
        normalized, ingestion, snapshot, bounds, manifest = frozen()
        manifest["comparison_qualification"] = qualify_frozen_index(normalized, ingestion, snapshot, bounds)
        manifest["geography"] = self.service.manifest["geography"]
        self.service.manifest = manifest
        self.saved["coverage_complete"] = False
        self.saved["comparison_scope"] = SCOPE
        self.saved["spec"]["periods"] = {
            "baseline": {"gte": "2025-05-01T00:00:00-04:00", "lt": "2025-06-01T00:00:00-04:00"},
            "current": {"gte": "2025-06-01T00:00:00-04:00", "lt": "2025-07-01T00:00:00-04:00"}}

    def test_qualified_observed_trends_publish_without_population_claim(self):
        self.observed_snapshot()
        result = publish_trend_map(self.service, self.saved, None)
        self.assertEqual(result["comparison_scope"], SCOPE)
        self.assertFalse(result["coverage_complete"])
        self.assertFalse(result["source_snapshot_coverage"]["complete"])
        self.assertTrue(any("not proof" in warning for warning in result["warnings"]))
        self.assertEqual(result["published_group_count"], 2)

    def test_saved_scope_alone_changed_certificate_or_outside_period_never_publishes(self):
        for change in ("certificate", "period", "scope", "complete", "execution", "missing_certificate"):
            with self.subTest(change=change):
                self.observed_snapshot()
                self.saved["execution_complete"] = True
                if change == "certificate": self.service.manifest["comparison_qualification"]["row_count"] = 3
                elif change == "period": self.saved["spec"]["periods"]["current"]["lt"] = "2025-08-01T00:00:00-04:00"
                elif change == "scope": self.saved["comparison_scope"] = "complete_declared_corpus"
                elif change == "complete": self.saved["coverage_complete"] = True
                elif change == "execution": self.saved["execution_complete"] = False
                else: self.service.manifest.pop("comparison_qualification")
                with self.assertRaises(AnalyticsError):
                    publish_trend_map(self.service, self.saved, None)
                self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
    unittest.main()
