import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.cli import main
from analytics311.errors import AnalyticsError
from analytics311.service import file_hash
from analytics311.workloads import normalize_file, source_manifest


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "raw.jsonl"
        self.source.write_text(json.dumps({"unique_key": "1", "created_date": "2025-12-01T12:00:00", "status": "Open"}) + "\n")
        self.manifest = {"sha256": file_hash(self.source), "row_count": 1, "kind": "public_sample",
                         "coverage": {"gte": "2025-12-01T05:00:00Z", "lt": "2025-12-02T05:00:00Z", "complete": False}}
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"backend": "elastic", "elastic_url": "http://127.0.0.1:9200",
            "allow_insecure_local": True, "index": "test-v1", "manifest_path": "frozen.json"}))

    def stage(self):
        self.source.with_suffix(".manifest.json").write_text(json.dumps(self.manifest))

    def invoke(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(["--config", str(self.config), "ingest", str(self.source), "--freeze", *extra])

    def test_changed_file_cannot_reuse_source_provenance(self):
        self.stage()
        self.source.write_text(self.source.read_text() + "\n")
        with self.assertRaises(AnalyticsError) as error:
            source_manifest(self.source)
        self.assertEqual(error.exception.code, "source_changed")

    def test_replacement_between_validation_and_read_cannot_keep_old_provenance(self):
        self.stage()
        destination=self.root/'changed.jsonl'
        with patch('analytics311.workloads.source_manifest',return_value=self.manifest), patch('analytics311.workloads.file_hash',return_value='new-content-hash'):
            with self.assertRaises(AnalyticsError) as error:
                normalize_file(self.source,destination)
        self.assertEqual(error.exception.code,'source_changed')
        self.assertFalse(destination.exists())

    def test_sample_cannot_be_asserted_complete_before_any_network_mutation(self):
        self.stage()
        with patch("analytics311.elastic.ElasticClient") as client:
            result = self.invoke("--coverage-start", "2025-12-01T05:00:00Z", "--coverage-end", "2025-12-02T05:00:00Z", "--complete-coverage", "--create-index")
        self.assertEqual(result, 2)
        client.assert_not_called()

    def test_invalid_dates_rejected_before_index_creation(self):
        for start, end in [("garbage", "2026-01-01T00:00:00Z"), ("2025-12-01", "2026-01-01"),
                           ("2026-01-01T00:00:00Z", "2025-12-01T00:00:00Z")]:
            with self.subTest(start=start), patch("analytics311.elastic.ElasticClient") as client:
                result = self.invoke("--coverage-start", start, "--coverage-end", end, "--create-index")
                self.assertEqual(result, 2)
                client.assert_not_called()

    def test_freeze_preserves_verified_geography_and_sample_kind(self):
        self.manifest["geography"] = {"nta_version": "boundary-hash"}
        self.stage()
        with patch("analytics311.elastic.ElasticClient"), patch("analytics311.ingest._ingest_jsonl_unlocked", return_value={"source_sha256": self.manifest["sha256"], "processed_rows": 1}), patch("analytics311.ingest.freeze_index", return_value={"index": "test-v1", "index_uuid": "uuid", "row_count": 1, "immutable": True}):
            result = self.invoke("--coverage-start", "2025-12-01T05:00:00Z", "--coverage-end", "2025-12-02T05:00:00Z", "--normalized-input")
        self.assertEqual(result, 0)
        frozen = json.loads((self.root / "frozen.json").read_text())
        self.assertEqual(frozen["geography"], self.manifest["geography"])
        self.assertEqual(frozen["kind"], "public_sample")
        self.assertFalse(frozen["coverage"]["complete"])

    def test_checkpoint_contention_blocks_cli_before_creation_or_source_reads(self):
        from analytics311.ingest import ingestion_lease
        checkpoint = self.root / "ingest.json"
        with ingestion_lease(checkpoint), patch("analytics311.elastic.ElasticClient") as client, \
                patch("analytics311.workloads.source_manifest") as source:
            code = self.invoke("--checkpoint", str(checkpoint), "--create-index",
                               "--coverage-start", "2025-12-01T05:00:00Z", "--coverage-end", "2025-12-02T05:00:00Z")
        self.assertEqual(2, code)
        client.assert_not_called()
        source.assert_not_called()
        self.assertFalse((self.root / "frozen.json").exists())

    def test_cli_keeps_checkpoint_lease_through_creation_freeze_and_manifest(self):
        from analytics311.ingest import ingestion_lease
        checkpoint = self.root / "ingest.json"
        self.stage()
        stages = []

        def assert_owned(stage):
            with self.assertRaises(AnalyticsError) as raised:
                with ingestion_lease(checkpoint):
                    pass
            self.assertEqual("ingestion_busy", raised.exception.code)
            stages.append(stage)

        def freeze(*args, **kwargs):
            assert_owned("freeze")
            return {"index": "test-v1", "index_uuid": "uuid", "row_count": 1, "immutable": True}

        from analytics311.cli import atomic_json
        def publish(path, value):
            assert_owned("manifest")
            atomic_json(path, value)

        with patch("analytics311.elastic.ElasticClient"), \
                patch("analytics311.ingest.create_index", side_effect=lambda *args: assert_owned("create")), \
                patch("analytics311.ingest._ingest_jsonl_unlocked", return_value={"source_sha256": self.manifest["sha256"], "processed_rows": 1}), \
                patch("analytics311.ingest.freeze_index", side_effect=freeze), \
                patch("analytics311.cli.atomic_json", side_effect=publish):
            code = self.invoke("--checkpoint", str(checkpoint), "--create-index",
                               "--coverage-start", "2025-12-01T05:00:00Z", "--coverage-end", "2025-12-02T05:00:00Z")
        self.assertEqual(0, code)
        self.assertEqual(["create", "freeze", "manifest"], stages)
        with ingestion_lease(checkpoint):
            self.assertTrue((self.root / "frozen.json").exists())

    def test_normalization_keeps_sample_provenance_and_does_not_hide_system_errors(self):
        self.stage()
        result = normalize_file(self.source, self.root / "out.jsonl")
        self.assertEqual(result["provenance"]["sha256"], self.manifest["sha256"])
        self.assertFalse(result["coverage"]["complete"])
        with patch("analytics311.ingest.normalize_record", side_effect=AnalyticsError("missing_dependency", "timezone data missing")):
            with self.assertRaises(AnalyticsError):
                normalize_file(self.source, self.root / "failure.jsonl")
        self.assertFalse((self.root / "failure.jsonl").exists())

    def test_complete_coverage_requires_no_dropped_rows(self):
        self.manifest["coverage"]["complete"] = True
        self.manifest["kind"] = "reconciled_capture"
        self.stage()
        result = normalize_file(self.source, self.root / "complete.jsonl")
        self.assertTrue(result["coverage"]["complete"])
        self.source.write_text(self.source.read_text() + 'not json\n')
        self.manifest.update(sha256=file_hash(self.source), row_count=2)
        self.stage()
        result = normalize_file(self.source, self.root / "incomplete.jsonl")
        self.assertFalse(result["coverage"]["complete"])

    def test_retained_but_unmapped_creation_dates_downgrade_coverage(self):
        self.source.write_text(json.dumps({"unique_key":"1", "created_date":"2025-11-02T01:30:00", "status":"Open"})+'\n')
        self.manifest.update(sha256=file_hash(self.source), kind='reconciled_capture')
        self.manifest['coverage']={'complete':True,'gte':'2025-11-01T00:00:00-04:00','lt':'2025-12-01T00:00:00-05:00'}
        self.stage()
        result=normalize_file(self.source,self.root/'dst.jsonl')
        self.assertEqual(result['row_count'],1)
        self.assertEqual(result['quality_counts']['ambiguous_created_date'],1)
        self.assertFalse(result['coverage']['complete'])
