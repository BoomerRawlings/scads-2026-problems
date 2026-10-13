import copy
import unittest

from analytics311.errors import AnalyticsError
from analytics311.qualification import (SCOPE, comparison_qualification,
                                       qualify_frozen_index, qualify_normalized_capture)


def manifests():
    counts = {"row_count": 2, "unique_count": 2, "max_updated_at": "2026-10-07T01:00:00+00:00",
              "revision_headers": {"x-soda2-truth-last-modified": "2026-10-07T02:00:00+00:00",
                                   "x-soda2-secondary-last-modified": "2026-10-07T02:00:00+00:00"}}
    metadata = {"id": "erm2-nwe9", "schema_sha256": "a" * 64, "rowsUpdatedAt": 123, "viewLastModified": 456}
    capture = {"dataset_version": "capture-test", "kind": "reconciled_public_capture", "source_kind": "real_public_records",
               "source_dataset": "erm2-nwe9", "source": "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
               "observed_complete": True, "extraction_complete": True, "transactional_source_snapshot": False,
               "sha256": "b" * 64, "bytes": 200, "row_count": 2, "unique_key_count": 2,
               "source_date_bounds": {"gte": "2025-04-01T00:00:00", "lt": "2025-11-01T00:00:00"},
               "coverage": {"gte": "2025-04-01T00:00:00-04:00", "lt": "2025-11-01T00:00:00-04:00",
                            "complete": False, "observed_complete": True},
               "reconciliation": {"initial_count": counts, "final_count": copy.deepcopy(counts),
                                  "initial_metadata": metadata, "final_metadata": copy.deepcopy(metadata),
                                  "captured_max_updated_at": counts["max_updated_at"]}}
    normalized = {"dataset_version": "normalized-test", "sha256": "c" * 64, "source_sha256": "b" * 64,
                  "bytes": 300, "row_count": 2, "provenance": capture, "coverage": {"complete": False},
                  "quality_counts": {"written": 2, "missing_closed_date": 1}}
    return capture, normalized


def frozen():
    capture, normalized = manifests()
    normalized["comparison_qualification"] = qualify_normalized_capture(capture, normalized)
    ingestion = {"complete": True, "quarantined": False, "normalized_input": True, "source_sha256": "c" * 64,
                 "processed_rows": 2, "quality_counts": {}, "index": "nyc311-2025-test", "index_uuid": "uuid-test"}
    snapshot = {"index": ingestion["index"], "index_uuid": ingestion["index_uuid"], "immutable": True, "row_count": 2}
    bounds = {"gte": "2025-05-01T00:00:00-04:00", "lt": "2025-07-01T00:00:00-04:00", "complete": False}
    manifest = {**snapshot, "provenance": normalized, "ingestion": ingestion, "coverage": bounds}
    return normalized, ingestion, snapshot, bounds, manifest


class QualificationTests(unittest.TestCase):
    def rejects(self, function, *args):
        with self.assertRaises(AnalyticsError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, "qualification_failed")

    def test_lossless_observation_qualifies_without_promoting_population_claim(self):
        capture, normalized = manifests()
        original = copy.deepcopy((capture, normalized))
        certificate = qualify_normalized_capture(capture, normalized)
        self.assertEqual(certificate["scope"], SCOPE)
        self.assertEqual(certificate["normalized_sha256"], normalized["sha256"])
        self.assertFalse(certificate["population_complete"])
        self.assertFalse(certificate["transactional_source_snapshot"])
        self.assertIn("not proof", certificate["warning"])
        self.assertEqual((capture, normalized), original)
        normalized["comparison_qualification"] = certificate
        self.assertEqual(comparison_qualification(normalized), certificate)

    def test_samples_and_operator_complete_flag_cannot_qualify(self):
        for change in ({"kind": "real_public_sample"}, {"observed_complete": False},
                       {"source": "https://example.com/erm2-nwe9.json"}, {"transactional_source_snapshot": True}):
            with self.subTest(change=change):
                capture, normalized = manifests()
                capture.update(change)
                self.rejects(qualify_normalized_capture, capture, normalized)
        capture, normalized = manifests()
        capture["coverage"]["complete"] = True
        self.rejects(qualify_normalized_capture, capture, normalized)

    def test_hash_chain_and_nested_provenance_must_match(self):
        for field, value in (("source_sha256", "d" * 64), ("sha256", "missing"), ("provenance", {})):
            with self.subTest(field=field):
                capture, normalized = manifests()
                normalized[field] = value
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_count_drift_duplicates_and_boolean_counts_rejected(self):
        for container, field, value in (("capture", "unique_key_count", 1), ("normalized", "row_count", 1),
                                        ("capture", "row_count", True), ("normalized", "row_count", True)):
            with self.subTest(container=container, field=field, value=value):
                capture, normalized = manifests()
                (capture if container == "capture" else normalized)[field] = value
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_unmapped_dates_or_rejected_rows_block_qualification(self):
        for flag in ("missing_created_date", "invalid_created_date", "ambiguous_created_date",
                     "nonexistent_created_date", "rejected", "invalid_json"):
            with self.subTest(flag=flag):
                capture, normalized = manifests()
                normalized["quality_counts"][flag] = 1
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_quality_counters_are_required_and_typed(self):
        for quality in (None, {}, {"written": 1}, {"written": 2, "missing_closed_date": -1},
                        {"written": 2, "rejected": False}):
            with self.subTest(quality=quality):
                capture, normalized = manifests()
                normalized["quality_counts"] = quality
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_missing_or_changed_source_reconciliation_rejected(self):
        for section in ("final_count", "final_metadata", "captured_max_updated_at"):
            with self.subTest(section=section):
                capture, normalized = manifests()
                capture["reconciliation"][section] = None
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_malformed_or_different_replica_observations_rejected(self):
        for revision in ({}, {"x-soda2-truth-last-modified": []},
                         {"x-soda2-truth-last-modified": "a", "x-soda2-secondary-last-modified": "b"}):
            with self.subTest(revision=revision):
                capture, normalized = manifests()
                for name in ("initial_count", "final_count"):
                    capture["reconciliation"][name]["revision_headers"] = revision
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_coverage_cannot_be_widened_or_shifted_from_local_source_window(self):
        for start in ("2025-03-01T00:00:00-05:00", "2025-04-01T00:00:00Z", "2025-04-01", "bad"):
            with self.subTest(start=start):
                capture, normalized = manifests()
                capture["coverage"]["gte"] = start
                self.rejects(qualify_normalized_capture, capture, normalized)

    def test_absent_certificate_is_unqualified_and_edited_certificate_fails(self):
        capture, normalized = manifests()
        self.assertIsNone(comparison_qualification(normalized))
        normalized["comparison_qualification"] = qualify_normalized_capture(capture, normalized)
        normalized["comparison_qualification"]["population_complete"] = True
        self.rejects(comparison_qualification, normalized)

    def test_frozen_subwindow_binds_count_identity_and_qualifies_without_full_coverage(self):
        normalized, ingestion, snapshot, bounds, manifest = frozen()
        certificate = qualify_frozen_index(normalized, ingestion, snapshot, bounds)
        manifest["comparison_qualification"] = certificate
        self.assertEqual(certificate["gte"], bounds["gte"])
        self.assertEqual(certificate["stage"], "frozen_index")
        self.assertEqual(comparison_qualification(manifest), certificate)
        self.assertFalse(manifest["coverage"]["complete"])

    def test_incomplete_or_raw_ingestion_cannot_publish_qualification(self):
        for change in ({"complete": False}, {"normalized_input": False}, {"quarantined": True},
                       {"source_sha256": "a" * 64}, {"processed_rows": 1}, {"index_uuid": "other"}):
            with self.subTest(change=change):
                normalized, ingestion, snapshot, bounds, _ = frozen()
                ingestion.update(change)
                self.rejects(qualify_frozen_index, normalized, ingestion, snapshot, bounds)

    def test_wrong_frozen_count_unfrozen_and_missing_identity_rejected(self):
        for change in ({"row_count": 1}, {"immutable": False}, {"index_uuid": None}, {"index": "other"}):
            with self.subTest(change=change):
                normalized, ingestion, snapshot, bounds, _ = frozen()
                snapshot.update(change)
                self.rejects(qualify_frozen_index, normalized, ingestion, snapshot, bounds)

    def test_frozen_bounds_must_remain_inside_observed_capture(self):
        for change in ({"gte": "2025-03-01T00:00:00-05:00"}, {"lt": "2026-01-01T00:00:00-05:00"}, {"complete": True}):
            with self.subTest(change=change):
                normalized, ingestion, snapshot, bounds, _ = frozen()
                bounds.update(change)
                self.rejects(qualify_frozen_index, normalized, ingestion, snapshot, bounds)

    def test_changed_staged_certificate_and_manifest_index_fail_runtime_revalidation(self):
        normalized, ingestion, snapshot, bounds, manifest = frozen()
        normalized["comparison_qualification"]["row_count"] = 3
        self.rejects(qualify_frozen_index, normalized, ingestion, snapshot, bounds)
        normalized, ingestion, snapshot, bounds, manifest = frozen()
        manifest["comparison_qualification"] = qualify_frozen_index(normalized, ingestion, snapshot, bounds)
        manifest["index_uuid"] = "replacement"
        self.rejects(comparison_qualification, manifest)


if __name__ == "__main__":
    unittest.main()
