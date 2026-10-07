"""Actual HTTP/MCP selective retrieval; scripted answers are not model accuracy."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_agent import HAS_MCP, abstention, finish, tool
from test_grounded_media import constrained_report
from evidence_catalog import EvidenceCatalog
if HAS_MCP:
    import local_agent as local


@contextmanager
def counted_server(actions=(), token_count=100, usage_count=100):
    calls, queue = [], iter(actions)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, value):
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            calls.append((self.path, None))
            self.reply({"data": [{"id": "scripted-local"}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            if self.path == "/apply-template":
                self.reply({"prompt": "PRIVATE_RENDERED_PROMPT"})
            elif self.path == "/tokenize":
                self.reply({"tokens": [1] * token_count})
            elif self.path == "/v1/chat/completions":
                answer = next(queue)
                if callable(answer):
                    answer = answer(body)
                self.reply({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
                            "usage": {"prompt_tokens": usage_count, "completion_tokens": 10}})
            else:
                self.send_error(404)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def write_dataset(path):
    path.mkdir()
    (path / "graph.json").write_text(json.dumps({"nodes": [
        {"id": "org", "name": "Organization", "aliases": []},
        {"id": "part", "name": "Component", "aliases": []}],
        "edges": [{"source": "org", "target": "part", "relation": "depends_on", "evidence_ids": ["proof"]}]}))
    (path / "manifest.json").write_text("[]")
    (path / "records.csv").write_text(
        "id,entity_id,title,date,text,subject,predicate,value\n"
        "proof,org,Dependency source,2034-01-02,The organization depends on component,org,dependency,part\n"
        "unread-a,part,Unselected source A,2034-01-03,UNREAD_BODY_SENTINEL_A,part,review,pending\n"
        "unread-b,part,Unselected source B,2034-01-04,UNREAD_BODY_SENTINEL_B,part,review,uncertain\n",
        encoding="utf-8")
    return path


def report_with_fixed(body, report):
    schema = body["response_format"]["schema"]
    result = constrained_report(schema, report)
    if "const" in schema["properties"]["summary"]:
        result["summary"] = schema["properties"]["summary"]["const"]
    return result


@unittest.skipUnless(HAS_MCP, "Install requirements.txt for local HTTP/MCP checks")
class LocalCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_catalog_blocks_pixels_before_actual_mcp_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = write_dataset(base / "data")
            report = abstention("org")
            report.update(status="insufficient_evidence", summary="Text-only profile did not inspect pixels.")
            actions = [tool("entity_search", query="org"), tool("read_media", evidence_id="proof"),
                       finish(report), lambda body: report_with_fixed(body, report)]
            with counted_server(actions) as (url, calls):
                output = await local.run("org", base / "run", data_dir=data, base_url=url, max_steps=4,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True)
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([entry["name"] for entry in trace], ["entity_search"])
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["scope_rejections"][0]["action"], "read_media")
            decision = next(payload for route, payload in calls if route == "/v1/chat/completions")
            actions_in_schema = [branch["properties"]["action"]["const"] for branch in decision["response_format"]["schema"]["oneOf"]]
            self.assertNotIn("read_media", actions_in_schema)

    def test_nested_source_fields_cannot_enable_catalog_reads_or_media(self):
        result = {"structuredContent": {"id": "proof", "kind": "text", "source": "proof.txt", "text": "Literal source.",
                  "entity_ids": ["org"], "untrusted_nested": {"id": "unread-a", "kind": "image", "media_path": "a.png"}}}
        known = {"proof", "unread-a", "unread-b"}
        self.assertEqual(local.observed_source_ids("read_evidence", result, known, retrieval_profile="catalog"), {"proof"})
        progress = {key: set() for key in (*local.SOURCE_READ_TOOLS, "media_ids", "available_media")}
        local.record_source_progress("read_evidence", {"evidence_id": "proof"}, result, known, progress,
                                     retrieval_profile="catalog")
        self.assertEqual(progress["media_ids"], set())
        graph = {"structuredContent": {"edges": [{"evidence_ids": ["proof"], "extra": {"evidence_ids": ["unread-a"]}}],
                                          "untrusted_nested": {"evidence_id": "unread-b"}}}
        self.assertEqual(local.observed_source_ids("traverse_relationships", graph, known, retrieval_profile="catalog"), {"proof"})

    def test_slow_trickle_cannot_extend_catalog_wall_deadline(self):
        class SlowHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                raw = b'{"data": [{"id": "slow-local"}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    for byte in raw:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(.04)
                except OSError:
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            engine = local.LocalModel(f"http://127.0.0.1:{server.server_port}/v1")
            engine.context_token_limit = 16384
            started = time.monotonic()
            with self.assertRaises(local.RunFailure) as caught:
                engine.identify(.10)
            self.assertEqual(caught.exception.code, "model_timeout")
            self.assertLess(time.monotonic() - started, .65, "Trickled bytes must not restart the wall deadline")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    async def test_actual_chain_inventory_does_not_read_or_cite_unselected_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = write_dataset(base / "data")
            options = {"query": "", "entity_ids": ["org", "part"], "max_items": 2, "max_bytes": 4096}
            with EvidenceCatalog(data) as catalog:
                first = catalog.page(**options)
            self.assertIsNotNone(first["next_cursor"])
            report = abstention("org")
            report.update(status="complete", title="Source-scoped dependency", summary="Source records a dependency.",
                          findings=[{"claim": "The source records a dependency on the component.",
                                     "evidence_ids": ["proof"], "qualification": "One supplied assertion, not independent verification."}])
            actions = [tool("entity_search", query="org"), tool("traverse_relationships", target="org", max_hops=1),
                       tool("catalog_evidence", **options, cursor=None), tool("read_evidence", evidence_id="proof"),
                       finish(report), tool("catalog_evidence", **options, cursor=first["next_cursor"]),
                       finish(report), lambda body: report_with_fixed(body, report)]
            with counted_server(actions) as (url, calls):
                output = await local.run("org", base / "run", data_dir=data, base_url=url, max_steps=8,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True, evidence_summary=True)
            metadata = json.loads((output / "run-metadata.json").read_text())
            saved = json.loads((output / "report.json").read_text())
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual(metadata["intent_rejections"], 1)
            self.assertEqual(metadata["retrieved_evidence_ids"], ["proof"])
            self.assertEqual(metadata["observed_evidence_ids"], ["proof", "unread-a", "unread-b"])
            self.assertTrue(metadata["workflow_coverage"]["complete"])
            self.assertEqual(len(metadata["workflow_coverage"]["catalog_receipts"]), 1)
            self.assertEqual([item["name"] for item in trace].count("catalog_evidence"), 2)
            self.assertNotIn("search_evidence", [item["name"] for item in trace])
            self.assertEqual(metadata["synthesis_facts"]["catalog_discovery"]["unread_catalog_ids"], ["unread-a", "unread-b"])
            self.assertTrue(any("2 discovered IDs remain unread" in value for value in saved["limitations"]))
            self.assertEqual(len(metadata["context_admissions"]), 8)
            self.assertTrue(all(item["usage_prompt_tokens"] == 100 for item in metadata["context_admissions"]))
            wire = json.dumps(calls)
            for sentinel in ("UNREAD_BODY_SENTINEL_A", "UNREAD_BODY_SENTINEL_B"):
                self.assertNotIn(sentinel, wire, "Catalog bodies must never become full evidence")
            self.assertNotIn("PRIVATE_RENDERED_PROMPT", json.dumps(metadata))
            final = [payload for route, payload in calls if route == "/v1/chat/completions"][-1]
            packet = json.loads(final["messages"][2]["content"])
            self.assertEqual([item["id"] for item in packet["EVIDENCE_RECORDS"]], ["proof"])
            self.assertTrue(packet["CATALOG_DISCOVERY"]["metadata_only"])
            for route, payload in calls:
                if route == "/apply-template":
                    self.assertIn("response_format", payload)

    async def test_context_overflow_is_saved_before_any_generation(self):
        with tempfile.TemporaryDirectory() as temporary, counted_server(token_count=800) as (url, calls):
            data = write_dataset(Path(temporary) / "data")
            with self.assertRaises(local.RunFailure) as caught:
                await local.run("org", Path(temporary) / "run", data_dir=data, base_url=url,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True, context_token_limit=1024)
            self.assertIn("context", caught.exception.code)
            self.assertNotIn("/v1/chat/completions", [route for route, _ in calls])
            metadata = json.loads((Path(temporary) / "run/run-metadata.json").read_text())
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(len(metadata["context_admissions"]), 1)
            self.assertNotIn("PRIVATE_RENDERED_PROMPT", json.dumps(metadata))

    async def test_catalog_options_reject_before_network(self):
        with tempfile.TemporaryDirectory() as temporary, counted_server() as (url, calls):
            options = [{}, {"grounded_media": True}, {"grounded_media": True, "compact_synthesis": True, "context_token_limit": True},
                       {"grounded_media": True, "compact_synthesis": True, "catalog_context_bytes": 4095}]
            for index, flags in enumerate(options):
                with self.assertRaises(local.RunFailure) as caught:
                    await local.run("org", Path(temporary) / str(index), base_url=url, retrieval_profile="catalog", **flags)
                self.assertEqual(caught.exception.code, "invalid_options")
            self.assertEqual(calls, [])

    async def test_unread_catalog_citation_rejected_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = write_dataset(base / "data")
            report = abstention("org")
            report.update(status="complete", findings=[{"claim": "Source records a dependency.",
                          "evidence_ids": ["proof"], "qualification": "Source claim only."}])
            def rejected(body):
                answer = report_with_fixed(body, report)
                answer["findings"][0]["evidence_ids"] = ["unread-a"]
                return answer
            actions = [tool("entity_search", query="org"), tool("traverse_relationships", target="org", max_hops=1),
                       tool("catalog_evidence", query="", entity_ids=["org", "part"]),
                       tool("read_evidence", evidence_id="proof"), finish(report), rejected,
                       finish(report), lambda body: report_with_fixed(body, report)]
            with counted_server(actions) as (url, calls):
                output = await local.run("org", base / "run", data_dir=data, base_url=url, max_steps=8,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["report_rejections"], 1)
            rejected_body = json.loads((output / "rejected-report-01.json").read_text())
            self.assertEqual(rejected_body["findings"][0]["evidence_ids"], ["unread-a"])
            self.assertEqual(json.loads((output / "report.json").read_text())["findings"][0]["evidence_ids"], ["proof"])

    async def test_actual_usage_cannot_exceed_preflight_budget(self):
        with counted_server([{"action": "finish", "arguments": {"status": "insufficient_evidence", "target": "org"}}],
                            token_count=100, usage_count=900) as (url, calls):
            engine = local.LocalModel(url, "scripted-local")
            engine.context_token_limit = 1024
            with self.assertRaises(local.RunFailure) as caught:
                engine.decide([{"role": "user", "content": "Investigate source claims."}], {"type": "object"}, 3)
            self.assertEqual(caught.exception.code, "context_limit")
            self.assertIsNone(engine.last_output_json)
            self.assertEqual(engine.last_context_admission["usage_prompt_tokens"], 900)


if __name__ == "__main__":
    unittest.main()
