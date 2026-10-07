"""Real loopback HTTP tests for the analyst journey and request boundaries."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from graphrag_discovery.records import DomainError
from graphrag_discovery.engine import Engine
from graphrag_discovery.resources import read_text
from graphrag_discovery.web import MAX_REQUEST_BYTES, create_server


class WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = create_server(Path(self.directory.name) / "workspace.sqlite3", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        status, headers, body = self.http("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.token = json.loads(body)["data"]["csrf_token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.directory.cleanup()

    def http(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, operation, body, *, headers=None):
        actual_headers = {
            "Content-Type": "application/json", "X-CSRF-Token": self.token,
            "Origin": self.server.origin,
        }
        actual_headers.update(headers or {})
        status, response_headers, raw = self.http("POST", "/api/" + operation, json.dumps(body), actual_headers)
        result = json.loads(raw) if response_headers["Content-Type"].startswith("application/json") else raw
        return status, result

    def publish_fixture(self, batch):
        manifest = json.loads(read_text("fixtures", "pump", "manifest.json"))
        entry = manifest["batches"][batch]
        status, ingested = self.post("ingest", {
            "corpus_id": manifest["corpus_id"], "idempotency_key": entry["id"],
            "records_jsonl": read_text("fixtures", "pump", entry["records"]),
        })
        self.assertEqual(status, 200, ingested)
        job_id = ingested["data"]["job_id"]
        status, staged = self.post("assertions", {
            "job_id": job_id, "assertions": json.loads(read_text("fixtures", "pump", entry["assertions"])),
        })
        self.assertEqual(status, 200, staged)
        status, published = self.post("publish", {"job_id": job_id, "label": entry["id"]})
        self.assertEqual(status, 200, published)
        return published["data"]

    def test_static_assets_and_security_headers(self):
        for route, marker in (("/", b"GraphRAG Discovery"), ("/app.js", b"X-CSRF-Token"), ("/styles.css", b"workspace-grid")):
            with self.subTest(route=route):
                status, headers, body = self.http("GET", route)
                self.assertEqual(status, 200)
                self.assertIn(marker, body)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(headers["X-Frame-Options"], "DENY")
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_host_origin_and_csrf_are_independent_boundaries(self):
        status, _, body = self.http("GET", "/api/bootstrap", headers={"Host": "attacker.example"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "host_rejected")
        status, result = self.post("status", {"corpus_id": "unknown"}, headers={"Origin": "https://attacker.example"})
        self.assertEqual((status, result["error"]["code"]), (403, "origin_rejected"))
        status, result = self.post("status", {"corpus_id": "unknown"}, headers={"X-CSRF-Token": "wrong"})
        self.assertEqual((status, result["error"]["code"]), (403, "csrf_rejected"))
        status, _, raw = self.http("POST", "/api/status", '{"corpus_id":"unknown"}', {"Content-Type": "application/json"})
        self.assertEqual((status, json.loads(raw)["error"]["code"]), (403, "csrf_rejected"))
        status, _, _ = self.http("GET", "/", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        status, result = self.post("status", {"corpus_id": "unknown"})
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["status"], "not_ready")

    def test_routes_cannot_escape_static_root_or_invoke_private_methods(self):
        for path in ("/../README.md", "/%2e%2e/README.md", "/static/../engine.py", "/graphrag_discovery/engine.py", "/api/search"):
            with self.subTest(path=path):
                status, _, _ = self.http("GET", path)
                self.assertEqual(status, 404)
        status, _ = self.post("_one", {"table": "events", "identifier": "x"})
        self.assertEqual(status, 404)
        status, result = self.post("export", {"run_id": "x", "destination": "../escape"})
        self.assertEqual((status, result["error"]["code"]), (400, "invalid_request"))
        status, _, headers = self.http("OPTIONS", "/api/search")
        self.assertEqual(status, 405)

    def test_json_size_type_and_complete_batch_validation(self):
        headers = {"Content-Type": "application/json", "X-CSRF-Token": self.token}
        for payload in ('{"corpus_id":"a","corpus_id":"b"}', '{"corpus_id":NaN}', '[1,2]', '{'):
            status, _, raw = self.http("POST", "/api/status", payload, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(raw)["error"]["code"], "invalid_json")
        status, result = self.post("status", {"corpus_id": "unknown"}, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = self.http("POST", "/api/status", b" " * (MAX_REQUEST_BYTES + 1), headers)
        self.assertEqual(status, 413)
        source = read_text("fixtures", "pump", "01-initial.jsonl") + '{"bad":}\n'
        status, result = self.post("ingest", {"corpus_id": "pump-fixture", "idempotency_key": "bad", "records_jsonl": source})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "invalid_jsonl")
        _, result = self.post("status", {"corpus_id": "pump-fixture"})
        self.assertEqual(result["data"]["jobs"], [])

    def test_actual_analyst_journey_and_bundle_integrity(self):
        first = self.publish_fixture(0)
        _, bootstrap_headers, bootstrap_raw = self.http("GET", "/api/bootstrap")
        self.assertEqual(json.loads(bootstrap_raw)["data"]["corpora"][0]["corpus_id"], "pump-fixture")
        status, search = self.post("search", {"corpus_id": "pump-fixture", "snapshot_id": first["snapshot_id"], "query": "Pump P", "mode": "graphrag"})
        self.assertEqual(status, 200, search)
        run = search["data"]
        self.assertEqual(run["items"][0]["assertion_id"], "a-initial")
        status, evidence = self.post("evidence", {"corpus_id": "pump-fixture", "snapshot_id": first["snapshot_id"], "assertion_id": "a-initial"})
        self.assertEqual(status, 200)
        self.assertEqual(evidence["data"]["text"], run["items"][0]["text"])
        status, saved = self.post("baseline_save", {"run_id": run["run_id"], "kind": "entity_neighborhood", "seed_entity_ids": ["pump-p"], "hops": 1})
        self.assertEqual(status, 200, saved)
        baseline_id = saved["data"]["baseline_id"]
        status, saved_findings = self.post("baseline_save", {"run_id": run["run_id"], "kind": "saved_findings"})
        self.assertEqual(status, 200, saved_findings)
        findings_baseline_id = saved_findings["data"]["baseline_id"]
        data = {"corpus_id": "pump-fixture", "snapshot_id": first["snapshot_id"], "title": "Operator review", "question": "Who operates Pump P?", "notes": "Hypothesis; inspect its support.", "run_ids": [run["run_id"]], "baseline_ids": [baseline_id]}
        status, investigation = self.post("investigation_save", {"data": data})
        self.assertEqual(status, 200, investigation)
        investigation_id = investigation["data"]["investigation_id"]
        self.publish_fixture(1)
        corrected = self.publish_fixture(2)
        status, compared = self.post("compare", {"baseline_id": baseline_id, "target_snapshot_id": corrected["snapshot_id"], "mode": "world_state_change", "knowledge_cutoff": corrected["published_at"], "valid_from_time": "2025-01-31T00:00:00Z", "valid_to_time": "2025-02-04T00:00:00Z"})
        self.assertEqual(status, 200, compared)
        world = compared["data"]
        self.assertEqual(world["changes"][0]["before"][0]["assertion_id"], "a-corrected")
        self.assertEqual(world["changes"][0]["after"][0]["assertion_id"], "b-corrected")
        for mode in ("knowledge_change", "source_change"):
            status, other = self.post("compare", {"baseline_id": findings_baseline_id, "target_snapshot_id": corrected["snapshot_id"], "mode": mode})
            self.assertEqual(status, 200, other)
            self.assertEqual(other["data"]["scope"]["mode"], mode)
            self.assertTrue(other["data"]["changes"])
        status, reopened = self.post("investigation_get", {"investigation_id": investigation_id})
        self.assertEqual(status, 200)
        self.assertEqual(reopened["data"]["snapshot_id"], first["snapshot_id"])
        status, exported = self.post("export", {"run_id": world["run_id"]})
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(exported)) as bundle:
            self.assertEqual(set(bundle.namelist()), {"manifest.json", "run.json", "evidence.json", "report.md"})
            manifest = json.loads(bundle.read("manifest.json"))
            for entry in manifest["files"]:
                payload = bundle.read(entry["path"])
                self.assertEqual(len(payload), entry["bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])

    def test_scope_mismatch_and_stale_update_are_typed(self):
        first = self.publish_fixture(0)
        status, result = self.post("search", {"corpus_id": "wrong-corpus", "snapshot_id": first["snapshot_id"], "query": "Pump", "mode": "lexical"})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "scope_mismatch")
        data = {"corpus_id": "pump-fixture", "snapshot_id": first["snapshot_id"], "title": "Review", "question": "Pump?"}
        _, result = self.post("investigation_save", {"data": data})
        data["investigation_id"] = result["data"]["investigation_id"]
        status, updated = self.post("investigation_save", {"data": data, "expected_version": 1})
        self.assertEqual(status, 200)
        status, stale = self.post("investigation_save", {"data": data, "expected_version": 1})
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"]["code"], "version_conflict")

    def test_server_refuses_external_interfaces(self):
        with self.assertRaises(DomainError) as error:
            create_server(Path(self.directory.name) / "other.sqlite3", host="0.0.0.0")
        self.assertEqual(error.exception.code, "invalid_host")
        self.assertFalse((Path(self.directory.name) / "other.sqlite3").exists())

    def test_local_search_rejects_missing_index_before_model_dispatch(self):
        self.publish_fixture(0)
        status, result = self.post("search_local", {
            "corpus_id": "pump-fixture", "query": "Pump P", "vector_index_id": "absent", "mode": "dense",
        })
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "not_found")

    def test_preview_returns_ephemeral_prefix_evidence_in_requested_snapshot(self):
        snapshot = self.publish_fixture(0)
        self.publish_fixture(1)
        status, response = self.post("preview", {"corpus_id": "pump-fixture", "query": "Pum",
                                                "snapshot_id": snapshot["snapshot_id"], "mode": "graphrag"})
        self.assertEqual(status, 200, response)
        preview = response["data"]
        self.assertEqual(preview["operation"], "preview")
        self.assertEqual(preview["scope"]["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual([item["assertion_id"] for item in preview["items"]], ["a-initial"])
        self.assertNotIn("run_id", preview)
        self.assertNotIn("next_cursor", preview)
        self.assertEqual(preview["usage"]["model_calls"], 0)
        with Engine(self.server.db_path) as engine:
            self.assertEqual(engine.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            self.assertEqual(engine.db.execute("SELECT COUNT(*) FROM cursors").fetchone()[0], 0)

    def test_preview_rejects_caller_budgets_vectors_and_invalid_wire_types(self):
        base = {"corpus_id": "pump-fixture", "query": "Pum"}
        invalid = [{"budget": {"max_scan": 100000}}, {"limit": 100}, {"page_size": 100},
                   {"vector_index_id": "index"}, {"query_vector": [1, 0]}, {"_preview": True},
                   {"mode": []}, {"corpus_id": []}, {"query": False}, {"snapshot_id": None}]
        for extra in invalid:
            with self.subTest(extra=extra), patch.object(Engine, "__init__", side_effect=AssertionError("Invalid preview reached Engine")):
                status, response = self.post("preview", dict(base, **extra))
            self.assertEqual((status, response["error"]["code"]), (400, "invalid_request"))
        self.publish_fixture(0)
        for extra, code in (({"mode": "dense"}, "unsupported_capability"),
                            ({"mode": "hybrid"}, "unsupported_capability"),
                            ({"query": "x"}, "invalid_query"),
                            ({"query": "x" * 257}, "invalid_query"),
                            ({"valid_time": "2025-01-10T00:00:00Z"}, "unsupported_temporal_query")):
            status, response = self.post("preview", dict(base, **extra))
            self.assertEqual((status, response["error"]["code"]), (400, code))

    def test_wire_types_fail_before_database_or_model_dispatch(self):
        cases = [("status", {"corpus_id": []}, "corpus_id"),
                 ("job", {"job_id": {"id": "job"}}, "job_id"),
                 ("search_local", {"corpus_id": "pump-fixture", "query": "Pump P", "vector_index_id": []}, "vector_index_id"),
                 ("evidence", {"corpus_id": "pump-fixture", "assertion_id": "a-initial", "history": "false"}, "history")]
        for operation, body, field in cases:
            with self.subTest(operation=operation), patch.object(Engine, "__init__", side_effect=AssertionError("Invalid request reached Engine")):
                status, result = self.post(operation, body)
            self.assertEqual((status, result["error"]["code"]), (400, "invalid_request"))
            self.assertEqual(result["error"]["details"]["field"], field)

    def test_boolean_string_cannot_authorize_publication_exclusions(self):
        record = json.loads(read_text("fixtures", "pump", "01-initial.jsonl"))
        invalid = dict(record, event_id="invalid-hash", document_id="invalid-document", content_sha256="0" * 64)
        _, response = self.post("ingest", {"corpus_id": "pump-fixture", "idempotency_key": "with-quarantine",
                                             "records_jsonl": json.dumps(record) + "\n" + json.dumps(invalid)})
        job_id = response["data"]["job_id"]
        self.assertEqual(response["data"]["rejected"], 1)
        status, rejected = self.post("publish", {"job_id": job_id, "allow_exclusions": "false"})
        self.assertEqual((status, rejected["error"]["code"]), (400, "invalid_request"))
        _, job = self.post("job", {"job_id": job_id})
        self.assertEqual(job["data"]["publication"], "pending")
        status, rejected = self.post("publish", {"job_id": job_id, "allow_exclusions": False})
        self.assertEqual((status, rejected["error"]["code"]), (400, "excluded_records"))
        status, published = self.post("publish", {"job_id": job_id, "allow_exclusions": True})
        self.assertEqual(status, 200)
        self.assertEqual(published["data"]["coverage"]["excluded_records"], 1)

    def test_boolean_is_not_an_investigation_revision_number(self):
        snapshot = self.publish_fixture(0)
        data = {"corpus_id": "pump-fixture", "snapshot_id": snapshot["snapshot_id"], "title": "Review", "question": "Pump?"}
        _, first = self.post("investigation_save", {"data": data})
        data["investigation_id"] = first["data"]["investigation_id"]
        status, rejected = self.post("investigation_save", {"data": data, "expected_version": True})
        self.assertEqual((status, rejected["error"]["code"]), (400, "invalid_request"))
        _, restored = self.post("investigation_get", {"investigation_id": data["investigation_id"]})
        self.assertEqual(restored["data"]["version"], 1)

    def test_run_get_restores_complete_retained_results_and_original_scope(self):
        self.publish_fixture(0)
        snapshot = self.publish_fixture(1)
        _, response = self.post("search", {"corpus_id": "pump-fixture", "query": "Pump P",
                                            "mode": "graphrag", "page_size": 1,
                                            "knowledge_cutoff": None, "valid_time": None})
        first_page = response["data"]
        self.assertEqual(len(first_page["items"]), 1)
        self.assertIsNotNone(first_page["next_cursor"])
        self.publish_fixture(2)
        status, response = self.post("run_get", {"run_id": first_page["run_id"]})
        restored = response["data"]
        self.assertEqual(status, 200)
        self.assertEqual(restored["scope"], first_page["scope"])
        self.assertEqual(restored["scope"]["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual(len(restored["items"]), first_page["total_returned"])
        self.assertEqual({item["assertion_id"] for item in restored["items"]}, {"a-planned", "b-planned"})
        self.assertEqual(restored["budget"], first_page["budget"])

    def test_evidence_exposes_pinned_scope_and_distinct_source_and_assertion_clocks(self):
        source = read_text("fixtures", "pump", "01-initial.jsonl")
        _, response = self.post("ingest", {"corpus_id": "pump-fixture", "idempotency_key": "source-only", "records_jsonl": source})
        _, response = self.post("publish", {"job_id": response["data"]["job_id"]})
        source_snapshot = response["data"]
        graph_snapshot = self.publish_fixture(0)
        status, response = self.post("evidence", {"corpus_id": "pump-fixture", "assertion_id": "a-initial"})
        evidence = response["data"]
        self.assertEqual(status, 200)
        self.assertEqual(evidence["scope"], {"corpus_id": "pump-fixture", "snapshot_id": graph_snapshot["snapshot_id"],
                                           "knowledge_cutoff": graph_snapshot["published_at"], "history": False})
        self.assertEqual(evidence["visible_from"], source_snapshot["published_at"])
        self.assertEqual(evidence["recorded_at"], graph_snapshot["published_at"])
        self.assertEqual(evidence["valid_from"], "2025-01-01T00:00:00.000000+00:00")
        self.assertEqual(evidence["temporal_status"], {"from": "known", "to": "open"})
        self.assertEqual(evidence["method"], "authored-fixture")
        self.assertEqual(evidence["source_status"], "active")
        self.assertEqual(evidence["modality"], "reported")
        self.assertFalse(evidence["disputed"])
        status, response = self.post("evidence", {"corpus_id": "pump-fixture", "assertion_id": "a-initial",
                                                  "knowledge_cutoff": source_snapshot["published_at"]})
        self.assertEqual((status, response["error"]["code"]), (400, "evidence_not_visible"))
        withdrawal = {"schema_version": "1", "event_id": "withdraw", "document_id": "operator-notice",
                      "version_id": "v1", "operation": "withdraw", "reason": "Publisher withdrawal", "access_scope": "public"}
        _, response = self.post("ingest", {"corpus_id": "pump-fixture", "idempotency_key": "withdraw",
                                            "records_jsonl": json.dumps(withdrawal)})
        _, response = self.post("publish", {"job_id": response["data"]["job_id"]})
        status, response = self.post("evidence", {"corpus_id": "pump-fixture", "assertion_id": "a-initial", "history": True})
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["source_status"], "withdrawn")
        self.assertEqual(response["data"]["modality"], "reported")
        self.assertTrue(response["data"]["scope"]["history"])

    def test_stalled_body_returns_typed_timeout_without_dispatch(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            with patch("graphrag_discovery.web.BODY_TIMEOUT_SECONDS", 0.05), patch.object(Engine, "get_corpus_status") as dispatch:
                connection.putrequest("POST", "/api/status")
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", "100")
                connection.putheader("X-CSRF-Token", self.token)
                connection.endheaders(b'{"corpus_id":')
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual((response.status, body["error"]["code"]), (408, "request_timeout"))
                dispatch.assert_not_called()
        finally:
            connection.close()
        status, response = self.post("status", {"corpus_id": "unknown"})
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["status"], "not_ready")

    def test_second_server_cannot_share_bound_port(self):
        with self.assertRaises(OSError):
            create_server(Path(self.directory.name) / "duplicate.sqlite3", port=self.port)

    def test_shutdown_joins_handler_after_export_body_before_database_close(self):
        snapshot = self.publish_fixture(0)
        _, response = self.post("search", {
            "corpus_id": "pump-fixture", "snapshot_id": snapshot["snapshot_id"],
            "query": "Pump P", "mode": "lexical",
        })
        exiting, release, closed = threading.Event(), threading.Event(), threading.Event()
        original_exit = Engine.__exit__

        def delayed_exit(engine, *args):
            exiting.set()
            release.wait(timeout=5)
            return original_exit(engine, *args)

        def close_server():
            self.server.server_close()
            closed.set()

        closer = threading.Thread(target=close_server, daemon=True)
        with patch.object(Engine, "__exit__", delayed_exit):
            try:
                status, body = self.post("export", {"run_id": response["data"]["run_id"]})
                self.assertEqual(status, 200)
                self.assertTrue(body.startswith(b"PK"))
                self.assertTrue(exiting.wait(timeout=2), "Export handler did not reach connection cleanup")
                self.server.shutdown()
                closer.start()
                self.assertFalse(closed.wait(timeout=0.1), "Server closed while the handler still owned its database connection")
            finally:
                release.set()
                if closer.ident is not None:
                    closer.join(timeout=3)
            self.assertTrue(closed.is_set(), "Server did not join the released handler")


if __name__ == "__main__":
    unittest.main()
