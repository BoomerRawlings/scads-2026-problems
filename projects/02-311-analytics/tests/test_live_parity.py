"""Runner/oracle unit checks. Faked transport NEVER supplies live evidence."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from analytics311.errors import AnalyticsError
from analytics311.fixture import FixtureBackend
from analytics311.service import AnalyticsService, file_hash
from tools import live_parity as parity


class LiveParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_id = "a" * 32
        self.index = f"analytics311-parity-{self.run_id}-v1"

    def identity_client(self, *, index_uuid="uuid-original", token=None):
        client = Mock()
        client.counts = {"pit_open": 0, "pit_close": 0, "record_continuations": 0, "composite_continuations": 0}

        def request(method, path, body=None):
            if path == "/":
                return {"version": {"number": "unit-test-only"}, "cluster_name": "private-cluster"}
            if path == f"/{self.index}" and method == "PUT":
                return {"index": self.index, "acknowledged": True}
            if path == f"/{self.index}/_settings":
                return {self.index: {"settings": {"index": {"uuid": index_uuid}}}}
            if path == f"/{self.index}/_mapping":
                return {self.index: {"mappings": {"_meta": {"parity_run_id": self.run_id if token is None else token}}}}
            if method == "DELETE":
                return {"acknowledged": True}
            raise AssertionError((method, path))

        client.request.side_effect = request
        return client

    def test_all_authored_cases_match_reference_and_hand_computed_metrics(self):
        source, _, _ = parity._prepare(self.root)
        service = AnalyticsService(self.root / "reference.json")
        self.assertEqual(len(source.read_text().splitlines()), 32)
        self.assertEqual(len(parity.cases()), 14)
        for case in parity.cases():
            with self.subTest(case=case["name"]):
                result = service.run_analysis(case["spec"])
                self.assertEqual(result["total"], {"value": len(case["expected_ids"]), "relation": "eq"})
                rows = parity._all_rows(service, result)
                parity._anchors(case["name"], rows)
                job = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
                observed = parity._csv_membership(job, case["expected_ids"])
                self.assertEqual(observed["rows"], len(case["expected_ids"]))

    def test_float_tolerance_never_hides_count_null_or_key_mismatch(self):
        self.assertTrue(parity._same({"mean": 3.5}, {"mean": 3.5000000001}))
        for observed in ({"count": 2.0}, {"count": True}, {"count": None}, {"count": 3}, {"count": 2, "extra": 0}):
            self.assertFalse(parity._same({"count": 2}, observed))
        for value in (float("nan"), float("inf"), 3.5001, None):
            self.assertFalse(parity._same(3.5, value))

    def csv_job(self, ids):
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["unique_key"])
            writer.writerows([[value] for value in ids])
        return {"status": "complete", "complete": True, "cohort_scope": "all_matching", "columns": ["unique_key"],
                "file": str(path), "rows_written": len(ids), "sha256": file_hash(path)}

    def test_same_count_wrong_membership_and_duplicate_ids_fail(self):
        for ids, code in ((["FIX-001", "FIX-001"], "duplicate_export_id"), (["FIX-001", "FIX-003"], "membership_mismatch")):
            with self.subTest(ids=ids), self.assertRaises(AnalyticsError) as failure:
                parity._csv_membership(self.csv_job(ids), ["FIX-001", "FIX-002"])
            self.assertEqual(failure.exception.code, code)

    def test_csv_checksum_and_job_completion_required(self):
        for changed in ({"sha256": "wrong"}, {"rows_written": 2}, {"complete": False}, {"cohort_scope": "selected_groups"}):
            job = {**self.csv_job(["FIX-001"]), **changed}
            with self.subTest(changed=changed), self.assertRaises(AnalyticsError):
                parity._csv_membership(job, ["FIX-001"])

    def test_cleanup_requires_current_invocation_creation(self):
        client = self.identity_client()
        with self.assertRaises(AnalyticsError):
            parity._cleanup_owned(client, self.index, self.run_id, "uuid-original", False)
        client.request.assert_not_called()

    def test_cleanup_refuses_arbitrary_name_before_any_request(self):
        client = self.identity_client()
        for name in ("production-v1", "*", "analytics311-parity-other-v1"):
            with self.subTest(name=name), self.assertRaises(AnalyticsError):
                parity._cleanup_owned(client, name, self.run_id, "uuid-original", True)
        client.request.assert_not_called()

    def test_cleanup_refuses_replaced_index_uuid_or_ownership(self):
        for client in (self.identity_client(index_uuid="uuid-replaced"), self.identity_client(token="another-run")):
            with self.assertRaises(AnalyticsError) as failure:
                parity._cleanup_owned(client, self.index, self.run_id, "uuid-original", True)
            self.assertEqual(failure.exception.code, "cleanup_refused")
            self.assertFalse(any(call.args[0] == "DELETE" for call in client.request.call_args_list))

    def test_cleanup_deletes_only_verified_concrete_index(self):
        client = self.identity_client()
        parity._cleanup_owned(client, self.index, self.run_id, "uuid-original", True)
        deletes = [call for call in client.request.call_args_list if call.args[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0].args[1], f"/{self.index}?expand_wildcards=none&allow_no_indices=false&ignore_unavailable=false")

    def test_no_provision_flag_means_no_client_or_files(self):
        with patch.object(parity, "TrackedClient") as constructor, self.assertRaises(AnalyticsError) as failure:
            parity.run_parity("http://localhost:9200", self.root / "out")
        self.assertEqual(failure.exception.code, "provisioning_not_authorized")
        constructor.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_existing_evidence_directory_never_overwritten(self):
        sentinel = self.root / "report.json"
        sentinel.write_text("preserve")
        with patch.object(parity, "TrackedClient") as constructor, self.assertRaises(AnalyticsError):
            parity.run_parity("http://localhost:9200", self.root, provision_fixture=True)
        constructor.return_value.request.assert_not_called()
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_index_creation_collision_never_ingests_or_deletes(self):
        client = self.identity_client()
        ordinary = client.request.side_effect

        def collision(method, path, body=None):
            if method == "PUT":
                raise AnalyticsError("backend_unavailable", "private existing index details")
            return ordinary(method, path, body)

        client.request.side_effect = collision
        with patch.object(parity, "TrackedClient", return_value=client), patch.object(parity, "uuid", Mock(uuid4=lambda: Mock(hex=self.run_id))), patch.object(parity, "ingest_jsonl") as ingest:
            report = parity.run_parity("http://localhost:9200", self.root / "out", provision_fixture=True, cleanup=True)
        self.assertFalse(report["passed"])
        self.assertFalse(report["index_creation_confirmed"])
        self.assertFalse(report["cleanup"]["deleted"])
        ingest.assert_not_called()
        self.assertFalse(any(call.args[0] == "DELETE" for call in client.request.call_args_list))
        saved = (self.root / "out/report.json").read_text()
        for private in ("private", "localhost", str(self.root)):
            self.assertNotIn(private, saved)

    def test_ingestion_failure_preserves_index_unless_explicit_owned_cleanup(self):
        for cleanup in (False, True):
            client = self.identity_client()
            with self.subTest(cleanup=cleanup), patch.object(parity, "TrackedClient", return_value=client), patch.object(parity, "uuid", Mock(uuid4=lambda: Mock(hex=self.run_id))), patch.object(parity, "ingest_jsonl", side_effect=AnalyticsError("partial_ingestion", "private message")):
                report = parity.run_parity("http://localhost:9200", self.root / str(cleanup), provision_fixture=True, cleanup=cleanup)
            self.assertFalse(report["passed"])
            self.assertEqual(report["error"], {"stage": "ingest", "code": "partial_ingestion"})
            self.assertTrue(report["index_creation_confirmed"])
            self.assertEqual(report["cleanup"]["deleted"], cleanup)
            self.assertEqual(any(call.args[0] == "DELETE" for call in client.request.call_args_list), cleanup)

    def test_shared_oracle_failure_precedes_network_and_mutation(self):
        client = self.identity_client()
        with patch.object(parity, "TrackedClient", return_value=client), patch.object(parity, "_anchors", side_effect=AnalyticsError("oracle_failed", "bad expected values")):
            report = parity.run_parity("http://localhost:9200", self.root / "out", provision_fixture=True)
        client.request.assert_not_called()
        self.assertFalse(report["passed"])
        self.assertFalse(report["real_data_verified"])
        self.assertFalse(report["agent_accuracy_verified"])

    def test_reference_substitution_cannot_satisfy_live_pagination_gate(self):
        # Test-only substitution exercises every comparison/export branch. It
        # must fail the actual-transport gate, and is never saved as evidence.
        client = self.identity_client()
        constructor = parity.AnalyticsService

        def substitute(path):
            service = constructor(path)
            if service.config["backend"] == "elastic":
                service.backend = FixtureBackend(service.config, service.catalog, service.manifest)
            return service

        frozen = {"index": self.index, "index_uuid": "uuid-original", "immutable": True, "row_count": 32}
        with patch.object(parity, "TrackedClient", return_value=client), patch.object(parity, "uuid", Mock(uuid4=lambda: Mock(hex=self.run_id))), patch.object(parity, "AnalyticsService", side_effect=substitute), patch.object(parity, "ingest_jsonl", return_value={"complete": True, "processed_rows": 32}), patch.object(parity, "freeze_index", return_value=frozen):
            report = parity.run_parity("http://localhost:9200", self.root / "out", provision_fixture=True, allow_insecure_local=True)
        self.assertEqual(len(report["cases"]), 14, report.get("error"))
        self.assertTrue(all(case["passed"] for case in report["cases"]))
        self.assertFalse(report["passed"])
        self.assertEqual(report["error"]["stage"], "pagination")
        self.assertFalse(report["scale_verified"])

    def test_transport_counters_require_successful_actual_request_method(self):
        client = parity.TrackedClient("http://localhost:9200", allow_insecure_local=True)
        with patch("analytics311.elastic.ElasticClient.request", return_value={}):
            client.request("POST", f"/{self.index}/_pit?keep_alive=1m")
            client.request("POST", "/_search", {"search_after": [1], "aggs": {"groups": {"composite": {"after": {"borough": None}}}}})
            client.request("DELETE", "/_pit", {"id": "test"})
        self.assertEqual(client.counts, {"pit_open": 1, "pit_close": 1, "record_continuations": 1, "composite_continuations": 1})
        with patch("analytics311.elastic.ElasticClient.request", side_effect=AnalyticsError("backend_unavailable", "test")), self.assertRaises(AnalyticsError):
            client.request("POST", f"/{self.index}/_pit?keep_alive=1m")
        self.assertEqual(client.counts["pit_open"], 1)


if __name__ == "__main__":
    unittest.main()
