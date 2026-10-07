"""CLI boundaries: whole-batch validation, JSON errors, and clock isolation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from graphrag_discovery.cli import main, read_jsonl
from graphrag_discovery.records import DomainError


class FakeEngine:
    def __init__(self, database):
        self.database = database
        self.closed = False
        self.last_call = None

    def close(self):
        self.closed = True

    def ingest(self, corpus, records, key):
        self.last_call = (corpus, records, key)
        return {"job_id": "job-1", "accepted": len(records), "text": records[0]["text"]}

    def get_corpus_status(self, corpus):
        raise DomainError("corpus_not_found", "No such corpus", {"corpus_id": corpus})

    def compare(self, baseline_id, **kwargs):
        self.last_call = (baseline_id, kwargs)
        return {"run_id": "comparison-1", "changes": [], "scope": kwargs}


class CliTests(unittest.TestCase):
    def invoke(self, args, factory):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(args, engine_factory=factory)
        self.assertEqual(error.getvalue(), "")
        return status, json.loads(output.getvalue())

    def test_later_bad_line_prevents_any_ingestion_or_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.jsonl"
            source.write_text('{"text":"valid first row"}\n{"text":}\n', encoding="utf-8")
            calls = []
            status, result = self.invoke(
                ["ingest", "--corpus", "test", "--file", str(source), "--key", "batch-1"],
                lambda path: calls.append(path),
            )
            self.assertEqual(status, 2)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "invalid_jsonl")
            self.assertEqual(result["error"]["details"]["line"], 2)
            self.assertEqual(calls, [])

    def test_strict_jsonl_rejects_ambiguous_and_nonstandard_records(self):
        cases = [
            '{"text":"first","text":"second"}\n',
            '{"metadata":{"score":NaN}}\n',
            '{"metadata":{"score":Infinity}}\n',
            '{}\n\n{}\n',
            '[]\n',
            '',
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.jsonl"
            for case in cases:
                with self.subTest(case=case):
                    source.write_text(case, encoding="utf-8")
                    with self.assertRaises(DomainError) as error:
                        read_jsonl(source)
                    self.assertEqual(error.exception.code, "invalid_jsonl")
            source.write_bytes(b'{"text":"\xff"}\n')
            with self.assertRaises(DomainError) as error:
                read_jsonl(source)
            self.assertEqual(error.exception.code, "invalid_jsonl")

    def test_valid_utf8_batch_is_unchanged_and_service_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.jsonl"
            record = {"text": "naïve survey 🧭\u2028second paragraph", "metadata": {"topic": "water"}}
            source.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            engine = FakeEngine("memory")
            status, result = self.invoke(
                ["ingest", "--corpus", "test", "--file", str(source), "--key", "batch-1"],
                lambda _: engine,
            )
            self.assertEqual(status, 0)
            self.assertEqual(result["data"]["text"], record["text"])
            self.assertEqual(engine.last_call, ("test", [record], "batch-1"))
            self.assertTrue(engine.closed)

    def test_parser_errors_have_json_envelope_and_no_engine_side_effect(self):
        calls = []
        status, result = self.invoke(
            ["search", "--corpus", "test", "--query", "pump", "--limit", "0"],
            lambda path: calls.append(path),
        )
        self.assertEqual(status, 2)
        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertEqual(calls, [])

    def test_ordinary_cli_has_no_trusted_clock_override(self):
        calls = []
        status, result = self.invoke(
            ["--clock", "2025-01-01T00:00:00Z", "init"],
            lambda path: calls.append(path),
        )
        self.assertEqual(status, 2)
        self.assertEqual(result["error"]["code"], "invalid_arguments")
        self.assertEqual(calls, [])

    def test_domain_error_preserves_code_details_and_closes_engine(self):
        engine = FakeEngine("memory")
        status, result = self.invoke(["status", "--corpus", "absent"], lambda _: engine)
        self.assertEqual(status, 2)
        self.assertEqual(result, {
            "ok": False,
            "error": {"code": "corpus_not_found", "message": "No such corpus", "details": {"corpus_id": "absent"}},
        })
        self.assertTrue(engine.closed)

    def test_fixed_knowledge_world_comparison_retains_all_time_constraints(self):
        engine = FakeEngine("memory")
        status, result = self.invoke([
            "compare", "--baseline", "base-1", "--target-snapshot", "snapshot-3",
            "--mode", "world_state_change", "--knowledge-cutoff", "2025-02-10T10:05:00Z",
            "--valid-from", "2025-01-31T00:00:00Z", "--valid-to", "2025-02-04T00:00:00Z",
            "--budget", '{"max_scan":12}',
        ], lambda _: engine)
        self.assertEqual(status, 0)
        self.assertEqual(engine.last_call[1]["knowledge_cutoff"], "2025-02-10T10:05:00Z")
        self.assertEqual(engine.last_call[1]["valid_from_time"], "2025-01-31T00:00:00Z")
        self.assertEqual(engine.last_call[1]["valid_to_time"], "2025-02-04T00:00:00Z")
        self.assertEqual(result["data"]["scope"]["budget"], {"max_scan": 12})

    def test_demo_refuses_to_overwrite_existing_database(self):
        from graphrag_discovery.demo import run_demo

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "existing.sqlite3"
            original = b"do not touch existing data"
            database.write_bytes(original)
            with self.assertRaises(DomainError) as error:
                run_demo(database, Path(directory) / "output")
            self.assertEqual(error.exception.code, "demo_requires_fresh_database")
            self.assertEqual(database.read_bytes(), original)
            self.assertFalse((Path(directory) / "output").exists())

    def test_real_cli_source_slice_reopens_exact_published_evidence(self):
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "pump" / "01-initial.jsonl"
        expected_text = read_jsonl(fixture)[0]["text"]
        with tempfile.TemporaryDirectory() as directory:
            prefix = ["--db", str(Path(directory) / "source.sqlite3")]
            status, ingested = self.invoke(prefix + [
                "ingest", "--corpus", "pump-fixture", "--file", str(fixture), "--key", "first",
            ], None)
            self.assertEqual(status, 0)
            status, published = self.invoke(prefix + ["publish", "--job", ingested["data"]["job_id"]], None)
            self.assertEqual(status, 0)
            snapshot_id = published["data"]["snapshot_id"]
            status, searched = self.invoke(prefix + [
                "search", "--corpus", "pump-fixture", "--snapshot", snapshot_id, "--query", "Pump P",
            ], None)
            self.assertEqual(status, 0)
            item = searched["data"]["items"][0]
            status, evidence = self.invoke(prefix + [
                "evidence", "--corpus", "pump-fixture", "--snapshot", snapshot_id, "--chunk", item["chunk_id"],
            ], None)
            self.assertEqual(status, 0)
            self.assertEqual(evidence["data"]["text"], expected_text)
            self.assertEqual(evidence["data"]["version_id"], "v1")
            self.assertEqual(searched["data"]["scope"]["snapshot_id"], snapshot_id)

    def test_real_demo_temporal_journey_and_export_file_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            status, result = self.invoke([
                "--db", str(Path(directory) / "demo.sqlite3"), "demo", "--output", str(output),
            ], None)
            self.assertEqual(status, 0)
            self.assertTrue(result["data"]["all_checks_passed"])
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["clock_mode"], "simulated_utc")
            self.assertEqual(report["extraction_method"], "authored-fixture")
            self.assertTrue(report["checks"]["withdrawn_c_has_retraction_evidence"])
            self.assertTrue(report["checks"]["fixed_knowledge_world_change_pairs_a_and_b"])
            for bundle in report["exports"].values():
                bundle_path = Path(bundle["destination"])
                manifest = json.loads((bundle_path / "manifest.json").read_text(encoding="utf-8"))
                for entry in manifest["files"]:
                    actual = (bundle_path / entry["path"]).read_bytes()
                    self.assertEqual(len(actual), entry["bytes"])
                    self.assertEqual(hashlib.sha256(actual).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
