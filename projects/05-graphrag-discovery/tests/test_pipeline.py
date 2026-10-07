"""Pipeline cache, provenance, and no partial publication on model failures."""
from pathlib import Path
import tempfile
import unittest

from graphrag_discovery.engine import Engine
from graphrag_discovery.records import DomainError
from tests.test_records import source, claim


class FakeLocalClient:
    profile = {"provider": "test-double", "model": "local-model", "prompt_version": "1"}
    def __init__(self, fail_at=None):
        self.calls, self.fail_at = 0, fail_at

    def extract(self, record, max_assertions=32):
        self.calls += 1
        if self.calls == self.fail_at:
            raise DomainError("local_model_unavailable", "Test transport failure")
        value = dict(claim(record), method="local-model-v1", assertion_id="model-"+record["document_id"], document_id=record["document_id"], version_id=record["version_id"])
        return {"assertions": [value], "metadata": {"provider": "test-double"}}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(Path(self.directory.name)/"db.sqlite3")
        self.addCleanup(self.engine.close)

    def ingest(self, records=None, key="first"):
        return self.engine.ingest("corpus", records or [source()], key)["job_id"]

    def test_local_extraction_stages_with_provenance_before_activation(self):
        job = self.ingest()
        result = self.engine.extract_job(job, FakeLocalClient())
        self.assertEqual(result["method"], "local-model-v1")
        self.assertEqual(self.engine.list_snapshots("corpus"), [])
        snapshot = self.engine.publish_snapshot(job)
        self.assertEqual(snapshot["coverage"]["method"], "local-model-and/or-authored")
        run = self.engine.search("corpus", "Pump", mode="graphrag")
        self.assertEqual(run["items"][0]["method"], "local-model-v1")

    def test_failure_retains_valid_cache_but_does_not_stage_partial_graph(self):
        records = [source(), dict(source(), document_id="second", event_id="second")]
        job = self.ingest(records)
        with self.assertRaises(DomainError):
            self.engine.extract_job(job, FakeLocalClient(fail_at=2))
        self.assertIsNone(self.engine._one("jobs", job)["assertions"])
        self.assertEqual(self.engine.list_snapshots("corpus"), [])
        client = FakeLocalClient()
        result = self.engine.extract_job(job, client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(result["extraction"]["cache_hits"], 1)
        self.assertEqual(result["assertions"], 2)

    def test_model_call_cap_stops_new_dispatch_and_retry_uses_cache(self):
        job = self.ingest([source(), dict(source(), document_id="second", event_id="second")])
        client = FakeLocalClient()
        with self.assertRaises(DomainError) as error:
            self.engine.extract_job(job, client, max_calls=1)
        self.assertEqual(error.exception.code, "extraction_budget_exhausted")
        self.assertEqual(client.calls, 1)
        self.assertIsNone(self.engine._one("jobs", job)["assertions"])
        result = self.engine.extract_job(job, FakeLocalClient(), max_calls=1)
        self.assertEqual(result["extraction"]["model_calls"], 1)

    def test_changed_source_context_prevents_cache_reuse(self):
        job = self.ingest()
        self.engine.extract_job(job, FakeLocalClient())
        records = [dict(source(), document_id="different", event_id="different", reference_time="2025-02-01T00:00:00Z")]
        client = FakeLocalClient()
        self.engine.extract_job(self.ingest(records, "second"), client)
        self.assertEqual(client.calls, 1)

    def test_direct_model_import_without_provenance_rejected(self):
        job = self.ingest()
        with self.assertRaises(DomainError) as error:
            self.engine.stage_assertions(job, [dict(claim(source()), method="local-model-v1")])
        self.assertEqual(error.exception.code, "missing_model_provenance")

    def test_closed_job_makes_no_model_calls(self):
        job = self.ingest()
        self.engine.cancel_job(job)
        client = FakeLocalClient()
        with self.assertRaises(DomainError):
            self.engine.extract_job(job, client)
        self.assertEqual(client.calls, 0)

    def test_local_abstention_does_not_publish_complete_graph_capability(self):
        client = FakeLocalClient()
        client.extract = lambda *a, **k: {"assertions": [], "metadata": {"abstained": True}}
        job = self.ingest()
        self.engine.extract_job(job, client)
        snapshot = self.engine.publish_snapshot(job)
        self.assertEqual(snapshot["coverage"]["extraction"], {"abstained": 1})
        self.assertFalse(snapshot["coverage"]["interpretation_complete"])
        self.assertNotIn("assertions", snapshot["capabilities"])
        self.assertEqual(len(self.engine.search("corpus", "Pump")["items"]), 1)

    def test_aggregate_deadline_clamps_call_timeout_and_restores_client(self):
        client = FakeLocalClient()
        client.timeout = 120
        observed = []
        extract = client.extract
        def bounded(*args, **kwargs):
            observed.append(client.timeout)
            return extract(*args, **kwargs)
        client.extract = bounded
        self.engine.extract_job(self.ingest(), client, max_wall_seconds=1)
        self.assertTrue(0 < observed[0] <= 1)
        self.assertEqual(client.timeout, 120)

    def test_unknown_model_dates_do_not_advertise_world_state_comparison(self):
        client = FakeLocalClient()
        extract = client.extract
        def unknown(*args, **kwargs):
            output = extract(*args, **kwargs)
            output["assertions"][0].update(valid_from=None, valid_to=None, temporal_status={"from": "unknown", "to": "unknown"})
            return output
        client.extract = unknown
        job = self.ingest()
        self.engine.extract_job(job, client)
        snapshot = self.engine.publish_snapshot(job)
        self.assertIn("assertions", snapshot["capabilities"])
        self.assertNotIn("world_compare", snapshot["capabilities"])
        result = self.engine.search("corpus", "Pump", mode="graphrag", valid_time="2025-02-01T00:00:00Z")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["coverage"]["unknown_time_assertions_excluded"], 1)
