"""Local runtime protocol/guard tests; scripted HTTP is not a model-quality eval."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HAS_MCP = importlib.util.find_spec("mcp") is not None
if HAS_MCP:
    import local_agent as local


def abstention(target="Delta"):
    return {"status": "needs_clarification", "title": "Identity unresolved", "target": target,
            "summary": "The alias has multiple matches. Please choose the intended entity.",
            "findings": [], "conflicts": [], "media_observations": [],
            "limitations": ["Identity ambiguity prevents a supported investigation."],
            "follow_up": ["Choose a canonical entity ID."]}


def tool(name, **arguments):
    return {"action": name, "arguments": arguments}


def finish(report):
    return tool("finish", status=report["status"], target=report["target"])


class RawModelOutput:
    def __init__(self, content, *, usage=None, reasoning_content=None, finish_reason="stop"):
        self.content = content
        self.usage = usage
        self.reasoning_content = reasoning_content
        self.finish_reason = finish_reason


@contextmanager
def model_server(actions=(), *, redirect=False, identifier="test-local-model", on_request=None):
    """Serve only the two local inference endpoints; preserve requests for assertions."""
    calls = []
    queue = iter(actions)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if on_request:
                on_request(self.path, None)
            if redirect:
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/paid-endpoint")
                self.end_headers()
            else:
                self.reply({"data": [{"id": identifier}]})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if on_request:
                on_request(self.path, payload)
            calls.append({"path": self.path, "payload": payload, "authorization": self.headers.get("Authorization")})
            action = next(queue, {"action": "unexpected"})
            content = action.content if isinstance(action, RawModelOutput) else json.dumps(action)
            response = {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
            if isinstance(action, RawModelOutput):
                response["choices"][0]["finish_reason"] = action.finish_reason
                if action.reasoning_content is not None:
                    response["choices"][0]["message"]["reasoning_content"] = action.reasoning_content
                if action.usage is not None:
                    response["usage"] = action.usage
            self.reply(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class LocalProtocolTests(unittest.TestCase):
    def test_decide_thinking_budget_defaults_boundaries_and_invalid_values(self):
        with model_server([{"answer": "ok"}] * 3) as (url, calls):
            engine = local.LocalModel(url, "test-local-model")
            engine.decide([], {"type": "object"}, 2)
            for budget in (1, 4096):
                engine.decide([], {"type": "object"}, 2, max_tokens=3072, thinking_budget=budget)
            default = calls[0]["payload"]
            self.assertEqual(default["max_tokens"], 512)
            self.assertEqual(default["temperature"], 0)
            self.assertEqual(default["seed"], 0)
            self.assertEqual(default["chat_template_kwargs"], {"enable_thinking": False})
            for key in ("reasoning_budget_tokens", "top_p", "top_k", "min_p", "presence_penalty"):
                self.assertNotIn(key, default)
            for budget, call in zip((1, 4096), calls[1:]):
                self.assertEqual(call["payload"]["max_tokens"], 3072 + budget)
                self.assertEqual(call["payload"]["reasoning_budget_tokens"], budget)
                self.assertEqual(call["payload"]["chat_template_kwargs"], {"enable_thinking": True})
            for budget in (-1, 4097, True, False, 1.5):
                with self.subTest(budget=budget), self.assertRaises(local.RunFailure):
                    engine.decide([], {"type": "object"}, 2, thinking_budget=budget)
            self.assertEqual(len(calls), 3, "Invalid budgets must fail before HTTP")

    def test_video_offsets_are_adaptive_failed_reads_retry_and_same_pts_do_not_alias(self):
        from jsonschema import ValidationError, validate

        progress = {key: set() for key in (*local.SOURCE_READ_TOOLS, "media_ids", "available_media")}
        media = {}
        inspect = {"structuredContent": {"evidence_id": "video", "available": True,
                   "mime_type": "video/mp4", "suggested_timestamps": [0, 14, 27]}}
        local.record_source_progress("inspect_media", {"evidence_id": "video"}, inspect, {"video"}, progress, media)

        def read(offsets, actual=None, failed=False):
            args, reason = local.prepare_media_args({"evidence_id": "video", "timestamps": offsets}, progress, media)
            self.assertIsNone(reason)
            samples = [{"requested_seek_seconds": t, "source_timestamp_seconds": t if actual is None else actual,
                        "source_pts": int((t if actual is None else actual) * 10), "source_time_base": "1/10"}
                       for t in args["timestamps"]]
            result = {"isError": failed, "content": [
                {"type": "text", "text": json.dumps({"evidence_id": "video", "samples": samples})},
                {"type": "image", "mimeType": "image/png", "data": "pixels"}]}
            local.record_source_progress("read_media", args, result, {"video"}, progress, media)

        read([0])
        read([14], failed=True)
        self.assertEqual(media["video"]["successful_requested_offsets"], {0})
        read([14])
        self.assertIn("video", local.eligible_source_actions({"video"}, progress, media)["read_media"])
        self.assertIn("already succeeded", local.prepare_media_args({"evidence_id": "video", "timestamps": [0]}, progress, media)[1])
        read([0, 27])
        for args in ({"evidence_id": "video"}, {"evidence_id": "video", "timestamps": None}):
            self.assertIn("already succeeded", local.prepare_media_args(args, progress, media)[1])
        read([0.1], actual=1)
        read([0.2], actual=1)
        self.assertEqual([(s["requested_seek_seconds"], s["source_timestamp_seconds"]) for s in media["video"]["samples"][-2:]],
                         [(0.1, 1), (0.2, 1)])
        self.assertEqual(media["video"]["samples"][-1]["source_time_base"], "1/10")
        for invalid in ([], [0, 1, 2, 3, 4], [-1], [3601], [10**400], [True], [float("nan")], [float("inf")]):
            with self.subTest(offsets=invalid):
                self.assertIsNotNone(local.prepare_media_args({"evidence_id": "video", "timestamps": invalid}, progress, media)[1])
        tools = [SimpleNamespace(name="read_media", inputSchema={"type": "object", "additionalProperties": False,
                 "properties": {"evidence_id": {"type": "string"}}, "required": ["evidence_id"]})]
        schema = local.action_schema(tools, eligible_reads=local.eligible_source_actions({"video"}, progress, media))
        validate(tool("read_media", evidence_id="video", timestamps=[0, 28]), schema)
        with self.assertRaises(ValidationError):
            validate(tool("read_media", evidence_id="video", timestamps=[0, 1, 2, 3, 4]), schema)

    def test_video_defaults_use_actual_inspection_and_missing_media_never_enable_reads(self):
        progress = {key: set() for key in (*local.SOURCE_READ_TOOLS, "media_ids", "available_media")}
        media = {}
        for eid, available, mime, samples in (("video", True, "video/mp4", [0, 8.25, 16.5]),
                                             ("image", True, "image/png", []),
                                             ("missing", False, "video/mp4", [0, 10])):
            result = {"structuredContent": {"evidence_id": eid, "available": available,
                      "mime_type": mime, "suggested_timestamps": samples}}
            local.record_source_progress("inspect_media", {"evidence_id": eid}, result, {eid}, progress, media)
        args, reason = local.prepare_media_args({"evidence_id": "video"}, progress, media)
        self.assertIsNone(reason)
        self.assertEqual(args["timestamps"], [0, 8.25, 16.5])
        self.assertIsNotNone(local.prepare_media_args({"evidence_id": "missing", "timestamps": [0]}, progress, media)[1])
        local.record_source_progress("read_media", {"evidence_id": "image"}, {"content": [{"type": "image"}]}, {"image"}, progress, media)
        self.assertIsNotNone(local.prepare_media_args({"evidence_id": "image", "timestamps": [14]}, progress, media)[1])
        self.assertEqual(local.eligible_source_actions(set(), progress, media)["read_media"], {"video"})

    def test_request_timeout_distinguished_from_connection_failure_without_raw_details(self):
        engine = local.LocalModel("http://127.0.0.1:1")
        cases = [(TimeoutError("private detail"), "model_timeout"),
                 (local.URLError(TimeoutError("private detail")), "model_timeout"),
                 (local.URLError(ConnectionRefusedError("private detail")), "model_unavailable")]
        for cause, code in cases:
            with self.subTest(code=code, cause=type(cause).__name__):
                with patch.object(engine.opener, "open", side_effect=cause):
                    with self.assertRaises(local.RunFailure) as error:
                        engine.request("/models", None, 0.1)
                self.assertEqual(error.exception.code, code)
                self.assertNotIn("private detail", str(error.exception))

    def test_graph_proof_ids_are_readable_but_not_report_citable_until_retrieved(self):
        from jsonschema import ValidationError, validate

        tools = [SimpleNamespace(name=name, inputSchema={"type": "object", "additionalProperties": False,
                 "properties": {"evidence_id": {"type": "string"}}, "required": ["evidence_id"]})
                 for name in sorted(local.SOURCE_READ_TOOLS)]
        graph = {"structuredContent": {"nodes": [{"id": "org"}], "edges": [{"evidence_ids": ["proof", "unknown"]}]}, "isError": False}
        known = {"proof", "unseen"}
        observed = local.observed_source_ids("traverse_relationships", graph, known)
        self.assertEqual(observed, {"proof"})
        self.assertEqual(local.observed_source_ids("traverse_relationships", {**graph, "isError": True}, known), set())
        self.assertEqual(local.observed_source_ids("entity_search", graph, known), set())
        graph_event = local._event("traverse_relationships", {"target": "org"}, graph)
        _, retrieved, _ = local.reports.collect_audit(json.dumps(graph_event), known)
        self.assertEqual(retrieved, set())
        progress = {key: set() for key in (*local.SOURCE_READ_TOOLS, "media_ids", "available_media")}
        initial = local.action_schema(tools, observed_ids=set(), retrieved_ids=set(),
                                      eligible_reads=local.eligible_source_actions(set(), progress))
        self.assertEqual([branch["properties"]["action"]["const"] for branch in initial["oneOf"]], ["finish"])
        after_graph = local.action_schema(tools, observed_ids=observed, retrieved_ids=retrieved,
                                          eligible_reads=local.eligible_source_actions(observed, progress))
        validate(tool("read_evidence", evidence_id="proof"), after_graph)
        for invalid in ("media/board.png", "unseen"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate(tool("read_evidence", evidence_id=invalid), after_graph)
        for name in ("inspect_media", "read_media"):
            with self.subTest(tool=name), self.assertRaises(ValidationError):
                validate(tool(name, evidence_id="proof"), after_graph)
        candidate = abstention("org")
        candidate["findings"] = [{"claim": "Source claim", "evidence_ids": ["proof"], "qualification": "Not independently verified."}]
        with self.assertRaises(ValidationError):
            validate(candidate, local.report_output_schema(finish(candidate)["arguments"], retrieved))
        read_event = local._event("read_evidence", {"evidence_id": "proof"}, {"structuredContent": {"id": "proof"}, "isError": False})
        _, retrieved, _ = local.reports.collect_audit(json.dumps(graph_event) + "\n" + json.dumps(read_event), known)
        after_read = local.report_output_schema(finish(candidate)["arguments"], retrieved)
        validate(candidate, after_read)
        candidate["findings"][0]["evidence_ids"] = ["unseen"]
        with self.assertRaises(ValidationError):
            validate(candidate, after_read)
        self.assertNotIn("enum", tools[0].inputSchema["properties"]["evidence_id"])

    def test_unresolved_report_grammar_excludes_citations_and_target_substitution(self):
        from jsonschema import ValidationError, validate

        schema = local.report_output_schema(finish(abstention())["arguments"], set(), unresolved_target="Delta")
        validate(abstention(), schema)
        for field, replacement in (("target", "delta_team"), ("status", "complete"),
                                   ("findings", [{"claim": "Unsupported", "evidence_ids": ["invented"], "qualification": ""}]),
                                   ("media_observations", [{"evidence_id": "invented", "locator": "image", "observation": "Unsupported"}])):
            candidate = abstention()
            candidate[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate(candidate, schema)
        intent_schema = local.action_schema([], "Delta")
        validate(finish(abstention()), intent_schema)
        with self.assertRaises(ValidationError):
            validate(finish(abstention("delta_team")), intent_schema)
        self.assertNotIn("report", intent_schema["oneOf"][-1]["properties"])

    def test_report_schema_locks_accepted_intent_and_citation_ids(self):
        from jsonschema import ValidationError, validate

        report = abstention("riverwatch")
        report["status"] = "insufficient_evidence"
        schema = local.report_output_schema(finish(report)["arguments"], {"memo-001"})
        validate(report, schema)
        for field, replacement in (("target", "cbri"), ("status", "complete")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate({**report, field: replacement}, schema)
        self.assertEqual(schema["properties"]["findings"]["items"]["properties"]["evidence_ids"]["items"]["enum"], ["memo-001"])

    def test_report_media_schema_excludes_indexed_unread_and_unretrieved_media(self):
        from jsonschema import ValidationError, validate

        report = abstention("org")
        report["status"] = "insufficient_evidence"
        indexed_only = {**report, "media_observations": [{"evidence_id": "indexed-image", "locator": "image", "observation": "Unseen pixels."}]}
        for media_reads in (None, {}, {"unretrieved-image": {"image"}}):
            with self.subTest(media_reads=media_reads):
                schema = local.report_output_schema(finish(report)["arguments"], {"indexed-image"}, media_reads=media_reads)
                self.assertEqual(schema["properties"]["media_observations"]["maxItems"], 0)
                validate(report, schema)
                with self.assertRaises(ValidationError):
                    validate(indexed_only, schema)

    def test_report_media_schema_accepts_only_inspected_pairs_with_canonical_locators(self):
        from jsonschema import ValidationError, validate

        report = abstention("org")
        report["status"] = "insufficient_evidence"
        retrieved = {"image-a", "video-a", "video-b", "indexed-only"}
        media_reads = {"image-a": {"image"}, "video-a": {0, 14.1234564, 59.9999996, 3661.000001},
                       "video-b": {9.25}, "unretrieved-image": {"image"}}
        schema = local.report_output_schema(finish(report)["arguments"], retrieved, media_reads=media_reads)
        branches = schema["properties"]["media_observations"]["items"]["oneOf"]
        pairs = {(branch["properties"]["evidence_id"]["const"], branch["properties"]["locator"]["const"])
                 for branch in branches}
        expected = {("image-a", "image"), ("video-a", "00:00"), ("video-a", "00:14.123456"),
                    ("video-a", "01:00"), ("video-a", "01:01:01.000001"), ("video-b", "00:09.25")}
        self.assertEqual(pairs, expected)
        evidence = {eid: {} for eid in retrieved}
        for eid, locator in sorted(expected):
            candidate = {**report, "media_observations": [{"evidence_id": eid, "locator": locator, "observation": "Inspected pixels."}]}
            with self.subTest(pair=(eid, locator)):
                validate(candidate, schema)
                local.reports.validate_report(candidate, evidence, retrieved, media_reads)
        for eid, locator in (("video-a", "00:09.25"), ("video-b", "00:14.123456"), ("video-a", "00:02"),
                             ("video-a", "image"), ("image-a", "00:00"), ("indexed-only", "image"),
                             ("unretrieved-image", "image")):
            candidate = {**report, "media_observations": [{"evidence_id": eid, "locator": locator, "observation": "Unsupported pixels."}]}
            with self.subTest(pair=(eid, locator)), self.assertRaises(ValidationError):
                validate(candidate, schema)
        empty_observation = {**report, "media_observations": [{"evidence_id": "image-a", "locator": "image", "observation": ""}]}
        with self.assertRaises(ValidationError):
            validate(empty_observation, schema)

    def test_only_loopback_no_credentials_or_redirects(self):
        self.assertEqual(local.local_base_url("http://localhost:8080"), "http://127.0.0.1:8080/v1")
        self.assertEqual(local.local_base_url("http://[::1]:8080/v1"), "http://[::1]:8080/v1")
        for endpoint in ("https://127.0.0.1", "http://example.com", "http://192.168.1.2",
                         "http://user:secret@127.0.0.1", "http://127.0.0.1/v1?key=secret", "http://127.0.0.1:0"):
            with self.subTest(endpoint=endpoint), self.assertRaises(local.RunFailure):
                local.local_base_url(endpoint)
        with model_server(redirect=True) as (url, _):
            with self.assertRaises(local.RunFailure) as error:
                local.LocalModel(url).identify(2)
            self.assertEqual(error.exception.code, "redirect_rejected")

    def test_discovery_selection_and_machine_path_redaction(self):
        with model_server(identifier=r"C:\private\model.gguf") as (url, _):
            metadata = local.LocalModel(url).identify(2)
            self.assertEqual(metadata["model"], "model.gguf")
            self.assertTrue(metadata["model_path_redacted"])
            self.assertNotIn("private", json.dumps(metadata))
            with self.assertRaises(local.RunFailure) as error:
                local.LocalModel(url, "other-model").identify(2)
            self.assertEqual(error.exception.code, "model_selection")

    def test_malformed_actions_and_limits_fail_closed(self):
        for action in ({"action": "shell", "arguments": {}}, {"action": "finish", "report": []},
                       {"action": "entity_search", "arguments": {"query": "x", "command": "x"}}, {"action": [], "arguments": {}}, []):
            with self.assertRaises(local.RunFailure):
                local.parse_action(action)
        with patch.object(local, "MAX_RESULT_BYTES", 32), self.assertRaises(local.RunFailure):
            local.result_message("search_evidence", {"content": [{"type": "text", "text": "x" * 100}]})
        with patch.object(local, "MAX_CONTEXT_BYTES", 32), self.assertRaises(local.RunFailure):
            local.LocalModel("http://127.0.0.1:1").request("/chat/completions", {"messages": "x" * 100}, 2)
        with model_server() as (url, _), patch.object(local, "MAX_RESPONSE_BYTES", 8):
            with self.assertRaises(local.RunFailure) as error:
                local.LocalModel(url).identify(2)
            self.assertEqual(error.exception.code, "response_limit")

    def test_pixels_and_source_timestamps_forwarded_but_not_audited_as_base64(self):
        result = {"content": [
            {"type": "text", "text": '{"evidence_id":"video-1", "media_path":"clip.mp4"}'},
            {"type": "text", "text": "Evidence video-1; sampled source frame at 4.000 seconds; no audio processing."},
            {"type": "image", "mimeType": "image/png", "data": "aW1hZ2U="}], "isError": False}
        message = local.result_message("read_media", result)
        self.assertIn("4.000", json.dumps(message))
        self.assertEqual(message["content"][-1]["image_url"]["url"], "data:image/png;base64,aW1hZ2U=")
        event = local._event("read_media", {"evidence_id": "video-1"}, result)
        self.assertNotIn("aW1hZ2U=", json.dumps(event))
        _, retrieved, inspected = local.reports.collect_audit(json.dumps(event), {"video-1"})
        self.assertEqual(retrieved, {"video-1"})
        self.assertEqual(inspected, {"video-1": {4.0}})

    def test_exact_successful_result_repeat_references_first_full_body(self):
        seen = {}
        args = {"entity_ids": ["org"], "query": "status"}
        result = {"isError": False, "structuredContent": {"records": [{"id": "source-1", "text": "UNIQUE_SOURCE_BODY"}]}}
        first, first_reference = local.result_feedback("search_evidence", args, result, 1, seen)
        repeated, reference = local.result_feedback("search_evidence", {"query": "status", "entity_ids": ["org"]},
                                                    {"structuredContent": result["structuredContent"], "isError": False}, 3, seen)
        self.assertIsNone(first_reference)
        self.assertEqual(len(seen), 1)
        fingerprint = next(iter(seen))
        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)
        self.assertEqual(seen[fingerprint], 1)
        self.assertEqual(reference, {"call": 3, "original_call": 1, "sha256": fingerprint})
        self.assertIn("UNIQUE_SOURCE_BODY", json.dumps(first))
        self.assertNotIn("UNIQUE_SOURCE_BODY", json.dumps(repeated))
        self.assertIn("MCP call 1", json.dumps(repeated))
        self.assertEqual(first["content"][1:], local.result_message("search_evidence", result)["content"][1:])
        third, third_reference = local.result_feedback("search_evidence", args, result, 5, seen)
        self.assertEqual(third_reference["original_call"], 1)
        self.assertNotIn("UNIQUE_SOURCE_BODY", json.dumps(third))
        with patch.object(local, "MAX_RESULT_BYTES", 16), self.assertRaises(local.RunFailure):
            local.result_feedback("search_evidence", args, result, 6, seen)

    def test_changed_tool_arguments_results_timestamps_and_pixels_remain_full(self):
        args = {"evidence_id": "video-1", "timestamps": [0]}
        result = {"isError": False, "content": [
            {"type": "text", "text": '{"evidence_id":"video-1","source_timestamp_seconds":0}'},
            {"type": "image", "mimeType": "image/png", "data": "cGl4ZWxz"}]}
        cases = [("inspect_media", args, result),
                 ("read_media", {**args, "evidence_id": "video-2"}, result),
                 ("read_media", {**args, "timestamps": [0.1]}, result),
                 ("read_media", args, {**result, "content": [
                     {"type": "text", "text": '{"evidence_id":"video-1","source_timestamp_seconds":1}'}, result["content"][1]]}),
                 ("read_media", args, {**result, "content": [result["content"][0],
                     {"type": "image", "mimeType": "image/png", "data": "bmV3LXBpeGVscw=="}]})]
        for index, (name, changed_args, changed_result) in enumerate(cases):
            with self.subTest(case=index):
                seen = {}
                local.result_feedback("read_media", args, result, 1, seen)
                feedback, reference = local.result_feedback(name, changed_args, changed_result, 2, seen)
                self.assertIsNone(reference)
                self.assertEqual(len(seen), 2)
                self.assertEqual(feedback["content"][1:], local.result_message(name, changed_result)["content"][1:])
        seen = {}
        first, _ = local.result_feedback("read_media", args, result, 1, seen)
        repeated, reference = local.result_feedback("read_media", args, result, 2, seen)
        self.assertIn("image_url", json.dumps(first))
        self.assertNotIn("image_url", json.dumps(repeated))
        self.assertNotIn("cGl4ZWxz", json.dumps(repeated))
        self.assertEqual(reference["original_call"], 1)

    def test_repeated_errors_always_retain_full_body_without_entering_reuse_index(self):
        seen = {}
        args = {"evidence_id": "missing"}
        result = {"isError": True, "content": [{"type": "text", "text": "FULL_ERROR_BODY"}]}
        for call in (1, 2):
            feedback, reference = local.result_feedback("read_evidence", args, result, call, seen)
            self.assertIsNone(reference)
            self.assertEqual(feedback["content"][1:], local.result_message("read_evidence", result)["content"][1:])
            self.assertIn("FULL_ERROR_BODY", json.dumps(feedback))
        self.assertEqual(seen, {})

    def test_synthesis_context_preserves_exact_source_errors_locators_and_pixels(self):
        messages = [local.result_message("search_evidence", {"isError": True,
                    "content": [{"type": "text", "text": "No matching source in requested scope."}]}),
                    local.result_message("read_evidence", {"structuredContent": {"id": "record-1", "text": "Source assertion."}}),
                    local.result_message("read_media", {"content": [
                        {"type": "text", "text": '{"evidence_id":"video-1","samples":[{"requested_seek_seconds":0.1,"source_timestamp_seconds":1.0}]}'},
                        {"type": "text", "text": "Evidence video-1; sampled source frame at 1.000000 seconds; no audio processing."},
                        {"type": "image", "mimeType": "image/png", "data": "aW1hZ2U="}]})]
        before = json.dumps(messages)
        schema = local.report_output_schema({"status": "insufficient_evidence", "target": "org"}, {"record-1", "video-1"})
        result = local.synthesis_messages(messages, "Which sources disagree?", "org", {"id": "test-corpus"}, schema)
        self.assertEqual(result[-len(messages):], messages)
        self.assertEqual(json.dumps(messages), before)
        self.assertEqual(sum(message["role"] == "system" for message in result), 1)
        self.assertFalse(any(message["role"] == "assistant" for message in result))
        self.assertIn("Which sources disagree?", json.dumps(result[:-len(messages)]))
        self.assertIn("test-corpus", json.dumps(result[:-len(messages)]))
        self.assertEqual(result[-1]["content"][-1]["image_url"]["url"], "data:image/png;base64,aW1hZ2U=")

    def test_synthesis_feedback_follows_sources_without_changing_them(self):
        sources = [local.result_message("read_evidence", {"structuredContent": {"id": "source-1", "text": "Original evidence."}})]
        schema = local.report_output_schema({"status": "insufficient_evidence", "target": "org"}, {"source-1"})
        reasons = ["Report cites media pixels or a frame not inspected through MCP"]
        result = local.synthesis_messages(sources, "What is supported?", "org", {"id": "test"}, schema, validation_reasons=reasons)
        self.assertEqual(result[2:3], sources)
        self.assertEqual(result[-1]["role"], "user")
        self.assertIn(reasons[0], json.dumps(result[-1]))
        self.assertFalse(any(message["role"] == "assistant" for message in result))

    @staticmethod
    def _facts_record(eid, kind="video_transcript", path=None):
        record = {"id": eid, "kind": kind, "entity_ids": ["org"], "source": "private-source.txt",
                  "text": "HISTORICAL NO VIDEO PROVIDED. This text cannot describe current tool calls."}
        if path is not None:
            record["media_path"] = path
        return record

    @staticmethod
    def _facts_event(name, args, body, *, pixels=False, **changes):
        result = {"content": [{"type": "text", "text": json.dumps(body)}]}
        if pixels:
            result["content"].append({"type": "image", "mimeType": "image/png", "data": "cHJpdmF0ZS1waXhlbHM="})
        event = local._event(name, args, result)
        event["item"].update(changes)
        return event

    def test_current_facts_separate_historical_text_attachment_inspection_and_actual_pixels(self):
        records = [self._facts_record("video", path="clip.mp4"), self._facts_record("image", "image_annotation", "board.png"),
                   self._facts_record("missing"), self._facts_record("uninspected"),
                   self._facts_record("unread", path="unread.mp4"), self._facts_record("plain", "text")]
        events = [self._facts_event("search_evidence", {"entity_ids": ["org"]}, {"query": "", "evidence": records})]
        for eid, available in (("video", True), ("image", True), ("missing", False)):
            events.append(self._facts_event("inspect_media", {"evidence_id": eid}, {"evidence_id": eid, "available": available}))
        events.extend([
            self._facts_event("read_media", {"evidence_id": "video", "timestamps": [14.5]},
                              {"evidence_id": "video", "media_path": "clip.mp4", "samples": [
                                  {"requested_seek_seconds": 14.5, "source_timestamp_seconds": 15.0},
                                  {"requested_seek_seconds": 20, "source_timestamp_seconds": 20.0}]}, pixels=True),
            self._facts_event("read_media", {"evidence_id": "image"},
                              {"evidence_id": "image", "media_path": "board.png"}, pixels=True),
        ])
        coverage = {"scope_entity_ids": ["org", "dependency"], "inventoried_entity_ids": ["org", "outside"]}
        with patch.object(local, "Workspace", side_effect=AssertionError("Facts must use actual events only")):
            facts = local.current_run_facts(events, coverage, {record["id"] for record in records},
                                            {"video": {15.0, 27.0}, "image": {"image"}, "unread": {1.0}})
        self.assertEqual(facts["policy"], "current-run-provenance-v1")
        self.assertEqual(facts["scope_entity_ids"], ["dependency", "org"])
        self.assertEqual(facts["inventoried_scope_entity_ids"], ["org"])
        self.assertEqual(facts["retrieved_source_ids"], sorted(record["id"] for record in records))
        media = {entry["evidence_id"]: entry for entry in facts["media"]}
        self.assertEqual(set(media), {"video", "image", "missing", "uninspected", "unread"})
        self.assertEqual(media["video"], {"evidence_id": "video", "attachment_declared": True,
                                       "inspected_available": True, "returned_pixel_locators": ["00:15"]})
        self.assertEqual(media["image"]["returned_pixel_locators"], ["image"])
        self.assertEqual(media["missing"], {"evidence_id": "missing", "attachment_declared": False,
                                         "inspected_available": False, "returned_pixel_locators": []})
        self.assertEqual(media["uninspected"], {"evidence_id": "uninspected", "attachment_declared": False,
                                             "returned_pixel_locators": []})
        self.assertEqual(media["unread"], {"evidence_id": "unread", "attachment_declared": True,
                                        "returned_pixel_locators": []})
        self.assertFalse(facts["audio_processed"])
        self.assertEqual(facts["video_coverage"], "sampled_frames_only")
        for payload in ("HISTORICAL", "private-source", "board.png", "clip.mp4", "cHJpdmF0ZS1waXhlbHM="):
            self.assertNotIn(payload, json.dumps(facts))

    def test_current_facts_ignore_failed_external_and_nested_source_claims(self):
        record = self._facts_record("known")
        record["nested"] = {"evidence_id": "known", "available": True, "media_path": "not-an-attachment.mp4"}
        base = self._facts_event("read_evidence", {"evidence_id": "known"}, record)
        invalid_groups = []
        for changes in ({"status": "failed"}, {"status": "in_progress"}, {"server": "other"}, {"error": {"message": "failure"}}):
            invalid_groups.extend([
                self._facts_event("read_evidence", {"evidence_id": "poison"}, self._facts_record("poison", path="bad.mp4"), **changes),
                self._facts_event("inspect_media", {"evidence_id": "known"}, {"evidence_id": "known", "available": True}, **changes),
            ])
        failed_result = self._facts_event("inspect_media", {"evidence_id": "known"}, {"evidence_id": "known", "available": True})
        failed_result["item"]["result"]["isError"] = True
        wrong_id = self._facts_event("inspect_media", {"evidence_id": "known"}, {"evidence_id": "other", "available": True})
        text_only = self._facts_event("search_evidence", {}, {"evidence": [{"id": "snippet", "kind": "video_transcript"}]})
        facts = local.current_run_facts([base, *invalid_groups, failed_result, wrong_id, text_only], {}, {"known", "snippet"}, {})
        self.assertEqual(facts["media"], [{"evidence_id": "known", "attachment_declared": False, "returned_pixel_locators": []}])
        self.assertEqual(facts["video_coverage"], "none")

    def test_current_facts_require_matching_successful_media_header_pixels_and_audit(self):
        source = self._facts_event("read_evidence", {"evidence_id": "video"}, self._facts_record("video", path="clip.mp4"))
        header = {"evidence_id": "video", "media_path": "clip.mp4", "samples": [{"source_timestamp_seconds": 15.0}]}
        bad_reads = [
            self._facts_event("read_media", {"evidence_id": "video"}, header, pixels=True, status="failed"),
            self._facts_event("read_media", {"evidence_id": "video"}, header, pixels=True, server="other"),
            self._facts_event("read_media", {"evidence_id": "video"}, header, pixels=True, error={"message": "failed"}),
            self._facts_event("read_media", {"evidence_id": "video"}, {**header, "evidence_id": "other"}, pixels=True),
            self._facts_event("read_media", {"evidence_id": "video"}, header),
            self._facts_event("read_media", {"evidence_id": "video"}, {"text": "sampled source frame at 15.000000 seconds"}, pixels=True),
        ]
        failed = self._facts_event("read_media", {"evidence_id": "video"}, header, pixels=True)
        failed["item"]["result"]["isError"] = True
        bad_reads.append(failed)
        for index, event in enumerate(bad_reads):
            with self.subTest(case=index):
                facts = local.current_run_facts([source, event], {}, {"video"}, {"video": {15.0}})
                self.assertEqual(facts["media"][0]["returned_pixel_locators"], [])
                self.assertEqual(facts["video_coverage"], "none")
        valid_read = self._facts_event("read_media", {"evidence_id": "video"}, header, pixels=True)
        for audited in ({}, {"video": {14.5}}, {"other": {15.0}}):
            with self.subTest(audited=audited):
                facts = local.current_run_facts([source, valid_read], {}, {"video"}, audited)
                self.assertEqual(facts["media"][0]["returned_pixel_locators"], [])
        image_source = self._facts_event("read_evidence", {"evidence_id": "image"}, self._facts_record("image", "image_annotation", "board.png"))
        image_read = self._facts_event("read_media", {"evidence_id": "image"}, {"evidence_id": "image", "media_path": "board.png"}, pixels=True)
        image_facts = local.current_run_facts([image_source, image_read], {}, {"image"}, {"image": {"image"}})
        self.assertEqual(image_facts["media"][0]["returned_pixel_locators"], ["image"])
        self.assertEqual(image_facts["video_coverage"], "none")

    def test_synthesis_current_facts_preamble_keeps_original_sources_errors_and_pixels(self):
        sources = [local.result_message("search_evidence", {"isError": True, "content": [{"type": "text", "text": "ORIGINAL_ERROR"}]}),
                   local.result_message("read_evidence", {"structuredContent": self._facts_record("video", path="clip.mp4")}),
                   local.result_message("read_media", {"content": [
                       {"type": "text", "text": '{"evidence_id":"video","samples":[{"source_timestamp_seconds":15}]}'},
                       {"type": "image", "mimeType": "image/png", "data": "cHJpdmF0ZS1waXhlbHM="}]})]
        before = json.dumps(sources)
        facts = {"policy": "current-run-provenance-v1", "scope_entity_ids": ["org"], "inventoried_scope_entity_ids": ["org"],
                 "retrieved_source_ids": ["video"], "media": [{"evidence_id": "video", "attachment_declared": True,
                 "inspected_available": True, "returned_pixel_locators": ["00:15"]}],
                 "audio_processed": False, "video_coverage": "sampled_frames_only"}
        schema = local.report_output_schema({"status": "insufficient_evidence", "target": "org"}, {"video"})
        result = local.synthesis_messages(sources, "What is supported?", "org", {"id": "test"}, schema,
                                          validation_reasons=["Previous report rejected."], current_facts=facts)
        self.assertEqual(json.loads(result[2]["content"]), {"CURRENT_RUN_FACTS": facts})
        self.assertEqual(result[3:3 + len(sources)], sources)
        self.assertEqual(json.dumps(sources), before)
        self.assertEqual(sum(message["role"] == "system" for message in result), 1)
        self.assertFalse(any(message["role"] == "assistant" for message in result))
        self.assertIn("Previous report rejected.", json.dumps(result[-1]))
        self.assertIn("HISTORICAL NO VIDEO PROVIDED", json.dumps(result[3:]))
        self.assertIn("ORIGINAL_ERROR", json.dumps(result[3:]))
        self.assertEqual(result[5]["content"][-1]["image_url"]["url"], "data:image/png;base64,cHJpdmF0ZS1waXhlbHM=")


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class LocalRunTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _coverage_fixture(data):
        data.mkdir()
        graph = {"nodes": [{"id": eid, "name": eid, "aliases": []} for eid in ("org", "dependency", "archive")],
                 "edges": [{"source": "org", "target": "dependency", "relation": "depends_on", "evidence_ids": ["edge-proof"]}]}
        (data / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (data / "manifest.json").write_text("[]", encoding="utf-8")
        (data / "records.csv").write_text(
            "id,entity_id,title,date,text,subject,predicate,value\n"
            "org-record,org,Status,2026-01-01,ready,org,status,ready\n"
            "dep-record,dependency,Dependency,2026-01-01,Pending review,dependency,status,unknown\n"
            "edge-proof,archive,Relationship source,2026-01-01,Organization depends on dependency,org,depends_on,dependency\n", encoding="utf-8")

    async def test_actual_inventory_and_outside_scope_proof_gate_report_generation(self):
        report = abstention("org")
        report.update(status="complete", summary="The source records a status.",
                      findings=[{"claim": "The organization record states ready.", "evidence_ids": ["org-record"], "qualification": "A source claim."}])
        actions = [tool("entity_search", query="org"), tool("traverse_relationships", target="org", max_hops=1),
                   tool("search_evidence", query="ready", entity_ids=["org", "dependency"]),
                   tool("read_evidence", evidence_id="org-record"), finish(report),
                   tool("search_evidence", entity_ids=["org", "dependency"]), finish(report),
                   tool("read_evidence", evidence_id="edge-proof"), finish(report), report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            data = Path(directory) / "corpus"
            self._coverage_fixture(data)
            output = await local.run("org", Path(directory) / "run", data_dir=data, base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["intent_rejections"], 2)
            self.assertIn('inventory entity IDs ["dependency", "org"]', metadata["validation_errors"][0])
            self.assertIn('retrieve full edge proof IDs ["edge-proof"]', metadata["validation_errors"][0])
            self.assertNotIn("inventory entity IDs", metadata["validation_errors"][1])
            self.assertIn('retrieve full edge proof IDs ["edge-proof"]', metadata["validation_errors"][1])
            coverage = metadata["workflow_coverage"]
            self.assertTrue(coverage["complete"])
            self.assertEqual(coverage["scope_entity_ids"], ["dependency", "org"])
            self.assertEqual(coverage["required_proof_ids"], ["edge-proof"])
            self.assertIn("edge-proof", coverage["retrieved_record_ids"])
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 9 + [3072])
            self.assertEqual(len(json.loads((output / "tool-trace.json").read_text())), 6)
            self.assertEqual(json.loads((output / "report.json").read_text()), report)

    async def test_incomplete_coverage_can_end_with_budgeted_insufficient_evidence(self):
        report = abstention("org")
        report.update(status="insufficient_evidence", summary="The action budget does not support further coverage.",
                      limitations=["Unfiltered inventory and relationship proof remain unexamined."])
        actions = [tool("entity_search", query="org"), tool("traverse_relationships", target="org", max_hops=1),
                   tool("search_evidence", query="ready", entity_ids=["org", "dependency"]),
                   tool("read_evidence", evidence_id="org-record"), tool("finish", status="complete", target="org"),
                   finish(report), report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            data = Path(directory) / "corpus"
            self._coverage_fixture(data)
            output = await local.run("org", Path(directory) / "run", data_dir=data, base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["status"], "insufficient_evidence")
            self.assertEqual(metadata["intent_rejections"], 1)
            self.assertFalse(metadata["workflow_coverage"]["complete"])
            self.assertEqual(metadata["workflow_coverage"]["missing_proof_ids"], ["edge-proof"])
            self.assertEqual(metadata["steps"], len(actions))
            self.assertEqual(sum(call["payload"]["max_tokens"] == 3072 for call in calls), 1)

    async def test_declared_target_only_scope_does_not_force_unreturned_descendant_media(self):
        report = abstention("org")
        report.update(status="complete", summary="The requested organization record states ready.",
                      findings=[{"claim": "The record states ready.", "evidence_ids": ["org-record"], "qualification": "Source claim; target-only scope."}])
        actions = [tool("entity_search", query="org"), tool("traverse_relationships", target="org", max_hops=0),
                   tool("search_evidence", entity_ids=["org"]), tool("read_evidence", evidence_id="org-record"),
                   finish(report), report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, _):
            data = Path(directory) / "corpus"
            self._coverage_fixture(data)
            (data / "child-note.txt").write_text("Unrequested descendant image annotation.", encoding="utf-8")
            (data / "child.png").write_bytes(b"outside-the-requested-scope")
            (data / "manifest.json").write_text(json.dumps([{"id": "child-image", "entity_ids": ["dependency"],
                "kind": "image_annotation", "title": "Child image", "date": "2026-01-01", "path": "child-note.txt",
                "media_path": "child.png", "assertions": [], "extraction": "authored_fixture"}]), encoding="utf-8")
            output = await local.run("org", Path(directory) / "run", data_dir=data, base_url=url, max_steps=len(actions),
                                     question="What does org-record state? Limit scope to org.")
            coverage = json.loads((output / "run-metadata.json").read_text())["workflow_coverage"]
            self.assertEqual(coverage["scope_entity_ids"], ["org"])
            self.assertTrue(coverage["complete"])
            self.assertEqual(coverage["required_proof_ids"], [])

    async def test_repeated_actual_mcp_search_keeps_both_calls_and_one_retained_body(self):
        report = abstention("riverwatch")
        report.update(status="insufficient_evidence", summary="The same evidence was retrieved twice; investigation stopped before full coverage.",
                      findings=[{"claim": "A readiness memo was retrieved.", "evidence_ids": ["memo-001"], "qualification": "Synthetic source claim."}])
        actions = [tool("search_evidence", entity_ids=["riverwatch"]), tool("search_evidence", entity_ids=["riverwatch"]),
                   finish(report), report]
        workspace = local.Workspace(local.reports.DATA)
        try:
            expected_ids = {item["id"] for item in workspace.search(entity_ids=["riverwatch"])}
        finally:
            workspace.close()
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual(trace, [{"name": "search_evidence", "args": {"entity_ids": ["riverwatch"]}, "status": "completed"}] * 2)
            self.assertEqual(metadata["steps"], len(actions))
            self.assertEqual(set(metadata["retrieved_evidence_ids"]), expected_ids)
            self.assertEqual({item["id"] for item in json.loads((output / "evidence-ledger.json").read_text())}, expected_ids)
            self.assertEqual(len(metadata["result_reuse"]), 1)
            reference = metadata["result_reuse"][0]
            self.assertEqual(reference["call"], 2)
            self.assertEqual(reference["original_call"], 1)
            self.assertEqual(len(reference["sha256"]), 64)
            int(reference["sha256"], 16)
            self.assertEqual(metadata["schema_policy"]["version"], "evidence-overview-opt-in-v11")
            self.assertEqual(json.loads(calls[-1]["payload"]["messages"][2]["content"]),
                             {"CURRENT_RUN_FACTS": metadata["synthesis_facts"]})
            retained = calls[-1]["payload"]["messages"][3:]
            self.assertEqual(len(retained), 2)
            body = retained[0]["content"][1:]
            self.assertTrue(body)
            self.assertEqual(sum(message["content"][1:] == body for message in retained), 1)
            self.assertIn("MCP call 1", json.dumps(retained[1]))
            self.assertNotIn("memo-001", json.dumps(retained[1]))
            self.assertEqual(json.loads((output / "report.json").read_text()), report)

    async def test_running_checkpoints_precede_requests_and_preserve_rejections(self):
        actions = [tool("traverse_relationships", target="delta_team"), tool("entity_search", query="Delta"),
                   finish(abstention("cbri")), finish(abstention()), abstention()]
        snapshots = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"

            def snapshot(path, payload):
                snapshots.append({"path": path, "metadata": json.loads((output / "run-metadata.json").read_text()),
                                  "trace": json.loads((output / "tool-trace.json").read_text())})

            with model_server(actions, on_request=snapshot) as (url, _):
                await local.run("Delta", output, base_url=url, max_steps=len(actions))
            self.assertEqual(len(snapshots), len(actions) + 1)
            self.assertTrue(all(s["metadata"]["status"] == "running" for s in snapshots))
            self.assertEqual(snapshots[0]["metadata"]["steps"], 0)
            self.assertEqual(snapshots[0]["trace"], [])
            self.assertEqual(len(snapshots[2]["metadata"]["scope_rejections"]), 1)
            self.assertEqual([call["name"] for call in snapshots[3]["trace"]], ["entity_search"])
            self.assertEqual(snapshots[4]["metadata"]["intent_rejections"], 1)
            self.assertEqual(snapshots[4]["metadata"]["report_rejections"], 0)
            self.assertIn("requested target", snapshots[4]["metadata"]["validation_errors"][0])
            self.assertEqual(snapshots[-2]["metadata"]["phase"], "decision")
            self.assertEqual(snapshots[-1]["metadata"]["phase"], "report")
            self.assertEqual(json.loads((output / "run-metadata.json").read_text())["status"], "needs_clarification")
            self.assertFalse(list(output.glob("*.tmp")))

    async def test_real_http_and_mcp_abstention_artifacts(self):
        actions = [tool("entity_search", query="Delta"), finish(abstention()), abstention()]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("Delta", Path(directory) / "run", base_url=url, max_steps=len(actions))
            self.assertEqual(json.loads((output / "report.json").read_text())["status"], "needs_clarification")
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["model"], "test-local-model")
            self.assertEqual(metadata["engine"], "local")
            self.assertIn("sha256", metadata["dataset"])
            self.assertEqual(len(metadata["implementation"]["files"]), 6)
            self.assertFalse((output / "failure.json").exists())
            self.assertTrue((output / "evidence-ledger.json").exists())
            self.assertTrue(all(call["authorization"] is None for call in calls))
            self.assertEqual({call["path"] for call in calls}, {"/v1/chat/completions"})
            self.assertEqual(calls[0]["payload"]["temperature"], 0)
            self.assertEqual(calls[0]["payload"]["seed"], 0)
            self.assertIn("oneOf", calls[0]["payload"]["response_format"]["schema"])
            self.assertIn("delta_team", json.dumps(calls[1]["payload"]["messages"]))
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512, 512, 3072])
            self.assertEqual(calls[-1]["payload"]["response_format"]["schema"]["properties"]["target"]["const"], "Delta")
            self.assertEqual(metadata["steps"], len(actions))
            for call in calls:
                self.assertEqual(call["payload"]["temperature"], 0)
                self.assertEqual(call["payload"]["chat_template_kwargs"], {"enable_thinking": False})
                self.assertNotIn("reasoning_budget_tokens", call["payload"])
            self.assertEqual(metadata["requested_report_thinking_budget"], 0)
            self.assertEqual(metadata["report_settings"], {
                "temperature": 0, "seed": 0, "max_tokens": 3072,
                "chat_template_kwargs": {"enable_thinking": False},
            })
            self.assertEqual(metadata["model_responses"], [
                {"step": 1, "phase": "decision", "usage": {}, "reasoning_returned": False},
                {"step": 2, "phase": "decision", "usage": {}, "reasoning_returned": False},
                {"step": 3, "phase": "report", "usage": {}, "reasoning_returned": False},
            ])

    async def test_report_thinking_only_opt_in_preserves_guards_and_sanitizes_response_metadata(self):
        secret = "DO_NOT_PERSIST_PRIVATE_REASONING_OR_USAGE"
        wrong_target = abstention("cbri")
        unobserved = abstention()
        unobserved["findings"] = [{"claim": "Unsupported source", "evidence_ids": ["tbl-001"], "qualification": ""}]
        planning_usage = {"prompt_tokens": 11, "completion_tokens": True, "total_tokens": "18",
                          "prompt_tokens_details": {"cached_tokens": 4, "private": secret},
                          "completion_tokens_details": {"reasoning_tokens": 2, "private": secret}, "private": secret}
        invalid_usage = {"prompt_tokens": -1, "completion_tokens": float("nan"), "total_tokens": float("inf"),
                         "prompt_tokens_details": {"cached_tokens": False},
                         "completion_tokens_details": {"reasoning_tokens": secret}, "private": secret}
        valid_usage = {"prompt_tokens": 25, "completion_tokens": 8, "total_tokens": 33,
                       "completion_tokens_details": {"reasoning_tokens": 5}}
        actions = [
            RawModelOutput(json.dumps(tool("entity_search", query="Delta")), usage=planning_usage, reasoning_content=secret),
            finish(abstention()), RawModelOutput("{", usage=invalid_usage, reasoning_content=secret),
            finish(abstention()), RawModelOutput(json.dumps(wrong_target), usage=secret, reasoning_content=secret),
            finish(abstention()), RawModelOutput(json.dumps(unobserved), usage={"private": secret}, reasoning_content=secret),
            finish(abstention()), RawModelOutput(json.dumps(abstention()), usage=valid_usage, reasoning_content=secret),
        ]
        budget = 256
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("Delta", Path(directory) / "run", base_url=url,
                                     max_steps=len(actions), report_thinking_budget=budget)
            metadata = json.loads((output / "run-metadata.json").read_text())
            settings = {"temperature": 0.6, "seed": 0, "max_tokens": 3072 + budget,
                        "chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget_tokens": budget,
                        "top_p": 0.95, "top_k": 20, "min_p": 0, "presence_penalty": 0}
            self.assertEqual(metadata["requested_report_thinking_budget"], budget)
            self.assertEqual(metadata["report_settings"], settings)
            report_steps = {3, 5, 7, 9}
            for step, call in enumerate(calls, 1):
                payload = call["payload"]
                if step in report_steps:
                    self.assertEqual({key: payload[key] for key in settings}, settings)
                else:
                    self.assertEqual(payload["max_tokens"], 512)
                    self.assertEqual(payload["temperature"], 0)
                    self.assertEqual(payload["seed"], 0)
                    self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
                    for key in ("reasoning_budget_tokens", "top_p", "top_k", "min_p", "presence_penalty"):
                        self.assertNotIn(key, payload)
            responses = metadata["model_responses"]
            self.assertEqual(len(responses), len(actions))
            self.assertEqual([entry["step"] for entry in responses], list(range(1, 10)))
            self.assertEqual([entry["phase"] for entry in responses],
                             ["report" if step in report_steps else "decision" for step in range(1, 10)])
            self.assertEqual(responses[0]["usage"], {"prompt_tokens": 11,
                             "prompt_tokens_details": {"cached_tokens": 4}, "completion_tokens_details": {"reasoning_tokens": 2}})
            self.assertEqual(responses[2]["usage"], {})
            self.assertEqual(responses[4]["usage"], {})
            self.assertEqual(responses[6]["usage"], {})
            self.assertEqual(responses[-1]["usage"], valid_usage)
            self.assertEqual([entry["reasoning_returned"] for entry in responses],
                             [True, False, True, False, True, False, True, False, True])
            self.assertEqual(metadata["report_rejections"], 3)
            reasons = " ".join(metadata["validation_errors"])
            self.assertIn("valid JSON", reasons)
            self.assertIn("target", reasons)
            self.assertIn("not retrieved", reasons)
            self.assertEqual(json.loads((output / "report.json").read_text()), abstention())
            self.assertEqual([entry["name"] for entry in json.loads((output / "tool-trace.json").read_text())], ["entity_search"])
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(secret, artifact.read_text(encoding="utf-8"), artifact.name)
            self.assertNotIn(secret, json.dumps([call["payload"]["messages"] for call in calls]))

    async def test_report_thinking_length_error_retains_usage_without_reasoning_or_partial_report(self):
        secret = "DO_NOT_PERSIST_REASONING_AFTER_LENGTH_ERROR"
        actions = [tool("entity_search", query="Delta"), finish(abstention()),
                   RawModelOutput("{" + secret, usage={"completion_tokens": 3200},
                                  reasoning_content=secret, finish_reason="length")]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure) as caught:
                await local.run("Delta", output, base_url=url, max_steps=len(actions), report_thinking_budget=128)
            self.assertEqual(caught.exception.code, "generation_limit")
            self.assertEqual(calls[-1]["payload"]["max_tokens"], 3200)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["model_responses"][-1], {
                "step": 3, "phase": "report", "usage": {"completion_tokens": 3200}, "reasoning_returned": True,
            })
            self.assertFalse((output / "report.json").exists())
            self.assertTrue((output / "failure.json").exists())
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(secret, artifact.read_text(encoding="utf-8"), artifact.name)

    async def test_invalid_report_thinking_budgets_fail_before_any_http(self):
        requests = []
        with tempfile.TemporaryDirectory() as directory, model_server(on_request=lambda path, payload: requests.append(path)) as (url, calls):
            for index, budget in enumerate((-1, 4097, True, False, 1.5)):
                with self.subTest(budget=budget), self.assertRaises(local.RunFailure):
                    await local.run("Delta", Path(directory) / f"run-{index}", base_url=url, report_thinking_budget=budget)
            self.assertEqual(requests, [])
            self.assertEqual(calls, [])

    async def test_target_and_unretrieved_citations_rejected_then_corrected(self):
        wrong_target = abstention("cbri")
        unobserved = abstention()
        unobserved["findings"] = [{"claim": "Unobserved claim", "evidence_ids": ["tbl-001"], "qualification": ""}]
        actions = [tool("entity_search", query="Delta"), finish(abstention()), wrong_target,
                   finish(abstention()), unobserved, finish(abstention()), abstention()]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, _):
            output = await local.run("Delta", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["report_rejections"], 2)
            self.assertIn("target", " ".join(metadata["validation_errors"]))
            self.assertIn("not retrieved", " ".join(metadata["validation_errors"]))

    async def test_media_rejection_feedback_reaches_next_synthesis_without_rejected_draft(self):
        from jsonschema import ValidationError, validate

        good = abstention("riverwatch")
        good.update(status="insufficient_evidence", summary="Only the retrieved board image was inspected.",
                    media_observations=[{"evidence_id": "img-note-001", "locator": "image", "observation": "The source image was inspected."}])
        draft_marker = "REJECTED_DRAFT_CONTENT_MUST_NOT_REENTER_SYNTHESIS"
        bad = {**good, "summary": draft_marker,
               "media_observations": [{"evidence_id": "video-tx-001", "locator": "00:14", "observation": draft_marker}]}
        actions = [tool("search_evidence", entity_ids=["missing"]), tool("search_evidence", entity_ids=["riverwatch"]),
                   tool("inspect_media", evidence_id="img-note-001"), tool("read_media", evidence_id="img-note-001"),
                   finish(bad), bad, finish(good), RawModelOutput("{"), finish(good), good]
        question = "Which evidence has actually been inspected?"
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, question=question, max_steps=len(actions))
            reports = [call["payload"] for call in calls if call["payload"]["max_tokens"] == 3072]
            self.assertEqual(len(reports), 3)
            for payload in reports:
                schema = payload["response_format"]["schema"]
                validate(good, schema)
                with self.assertRaises(ValidationError):
                    validate(bad, schema)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["report_rejections"], 2)
            self.assertEqual(metadata["schema_policy"]["version"], "evidence-overview-opt-in-v11")
            reasons = metadata["report_validation_errors"]
            self.assertEqual(len(reasons), 2)
            self.assertIn("not inspected", reasons[0])
            second_context = reports[1]["messages"]
            self.assertEqual(second_context[-1]["role"], "user")
            self.assertIn(reasons[0], json.dumps(second_context[-1]))
            self.assertNotIn(draft_marker, json.dumps(second_context))
            self.assertIn(question, json.dumps(second_context))
            self.assertFalse(any(message["role"] == "assistant" for message in second_context))
            self.assertEqual(second_context[2:-1], reports[0]["messages"][2:])
            self.assertIn("isError=True", json.dumps(second_context[2:-1]))
            self.assertIn("image_url", json.dumps(second_context[2:-1]))
            final_context = reports[-1]["messages"]
            for reason in reasons:
                self.assertIn(reason, json.dumps(final_context[-1]))
            self.assertNotIn(draft_marker, json.dumps(final_context))
            self.assertEqual(metadata["rejected_reports"], [{"path": "rejected-report-01.json", "reason": reasons[0]}])
            self.assertEqual(json.loads((output / "rejected-report-01.json").read_text()), bad)
            self.assertFalse((output / "rejected-report-02.json").exists())
            self.assertEqual(len(list(output.glob("rejected-report-*.json"))), 1)
            self.assertEqual(json.loads((output / "report.json").read_text()), good)

    async def test_no_media_rejects_completion_intent_without_report_generation(self):
        report = abstention("riverwatch")
        report.update(status="complete", findings=[{"claim": "A source reports delay.", "evidence_ids": ["memo-001"], "qualification": "Source claim."}])
        actions = [tool("entity_search", query="riverwatch"), tool("traverse_relationships", target="riverwatch", max_hops=3),
                   tool("search_evidence", entity_ids=["riverwatch", "silt_sensors", "northline"]),
                   tool("read_evidence", evidence_id="memo-001"), finish(report)]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure) as error:
                await local.run("riverwatch", output, base_url=url, max_steps=5)
            self.assertEqual(error.exception.code, "step_limit")
            self.assertFalse((output / "report.json").exists())
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertIn("inspect available relevant source media", " ".join(metadata["validation_errors"]))
            self.assertEqual(metadata["intent_rejections"], 1)
            self.assertEqual(metadata["report_rejections"], 0)
            self.assertTrue(all(call["payload"]["max_tokens"] == 512 for call in calls))

    async def test_completed_investigation_requests_report_after_actual_tools_and_pixels(self):
        report = abstention("riverwatch")
        report.update(status="complete", title="Source inspection", summary="The investigation retrieved source evidence and sampled attached media.",
                      findings=[{"claim": "The memo provides a readiness update.", "evidence_ids": ["memo-001"], "qualification": "Synthetic source claim."}],
                      media_observations=[{"evidence_id": "img-note-001", "locator": "image", "observation": "A board image was sampled."},
                                          {"evidence_id": "video-tx-001", "locator": "00:00", "observation": "The first source frame was sampled."}],
                      limitations=["Scripted protocol test; no model-quality claim."], follow_up=[])
        actions = [tool("entity_search", query="riverwatch"), tool("traverse_relationships", target="riverwatch", max_hops=3),
                   tool("search_evidence", entity_ids=["riverwatch", "silt_sensors", "northline"]),
                   tool("read_evidence", evidence_id="memo-001"), tool("inspect_media", evidence_id="img-note-001"),
                   tool("read_media", evidence_id="img-note-001"), tool("inspect_media", evidence_id="video-tx-001"),
                   tool("read_media", evidence_id="video-tx-001", timestamps=[0]), finish(report), report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            self.assertEqual(json.loads((output / "report.json").read_text()), report)
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * (len(actions) - 1) + [3072])
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual(len(trace), 8)
            self.assertTrue(all(call["status"] == "completed" for call in trace))
            self.assertNotIn("finish", [call["name"] for call in trace])
            self.assertIn("image_url", json.dumps(calls[-1]["payload"]["messages"]))
            planner_context = calls[-2]["payload"]["messages"]
            source_messages = [message for message in planner_context if message["role"] == "user"
                               and isinstance(message["content"], list)
                               and "UNTRUSTED TOOL RESULT:" in message["content"][0].get("text", "")]
            report_context = calls[-1]["payload"]["messages"]
            synthesis_sources = report_context[-len(source_messages):]
            # Planner-only countdowns may differ; every actual tool block must match.
            self.assertEqual([message["content"][1:] for message in synthesis_sources],
                             [message["content"][1:] for message in source_messages])
            self.assertFalse(any(message["role"] == "assistant" for message in report_context))
            self.assertNotIn(planner_context[0], report_context)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["intent_rejections"], 0)
            self.assertEqual(metadata["report_rejections"], 0)
            self.assertEqual(metadata["steps"], len(actions))
            self.assertIn("synthesis_context_policy", metadata)
            facts = metadata["synthesis_facts"]
            self.assertEqual(facts["policy"], "current-run-provenance-v1")
            self.assertEqual(facts["scope_entity_ids"], ["northline", "riverwatch", "silt_sensors"])
            self.assertEqual(facts["inventoried_scope_entity_ids"], facts["scope_entity_ids"])
            self.assertIn("memo-001", facts["retrieved_source_ids"])
            media = {entry["evidence_id"]: entry for entry in facts["media"]}
            self.assertEqual(media["img-note-001"]["returned_pixel_locators"], ["image"])
            self.assertEqual(media["video-tx-001"]["returned_pixel_locators"], ["00:00"])
            self.assertTrue(media["img-note-001"]["inspected_available"])
            self.assertTrue(media["video-tx-001"]["attachment_declared"])
            self.assertFalse(media["img-note-002"]["attachment_declared"])
            self.assertNotIn("inspected_available", media["img-note-002"])
            self.assertEqual(media["img-note-002"]["returned_pixel_locators"], [])
            self.assertFalse(facts["audio_processed"])
            self.assertEqual(facts["video_coverage"], "sampled_frames_only")
            self.assertEqual(json.loads(report_context[2]["content"]), {"CURRENT_RUN_FACTS": facts})

    async def test_malformed_decision_and_report_recover_via_planning(self):
        actions = [{"action": "not_a_tool", "arguments": {}}, tool("entity_search", query="Delta"),
                   finish(abstention()), {"status": "needs_clarification"}, finish(abstention()), abstention()]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("Delta", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertTrue(metadata["invalid_actions"])
            self.assertEqual(metadata["report_rejections"], 1)
            self.assertEqual(metadata["status"], "needs_clarification")
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512, 512, 512, 3072, 512, 3072])
            self.assertEqual([call["name"] for call in json.loads((output / "tool-trace.json").read_text())], ["entity_search"])

    async def test_report_cannot_change_accepted_status_even_if_schema_is_ignored(self):
        report = abstention("riverwatch")
        report["status"] = "insufficient_evidence"
        changed = {**report, "status": "needs_clarification"}
        actions = [tool("entity_search", query="riverwatch"), finish(report), changed, finish(report), report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["report_rejections"], 1)
            self.assertEqual(metadata["status"], "insufficient_evidence")
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512, 512, 3072, 512, 3072])

    async def test_last_action_finish_does_not_exceed_budget_to_generate_report(self):
        actions = [tool("entity_search", query="Delta"), finish(abstention()), abstention()]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure) as error:
                await local.run("Delta", output, base_url=url, max_steps=2)
            self.assertEqual(error.exception.code, "step_limit")
            self.assertEqual(len(calls), 2)
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512, 512])
            self.assertFalse((output / "report.json").exists())
            self.assertEqual(json.loads((output / "run-metadata.json").read_text())["steps"], 2)

    async def test_tool_errors_visible_and_previous_output_preserved(self):
        incomplete = abstention("riverwatch")
        incomplete["status"] = "insufficient_evidence"
        actions = [tool("search_evidence", entity_ids=["missing"]), tool("entity_search", query="riverwatch"),
                   finish(incomplete), incomplete]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            self.assertIn("isError=True", json.dumps(calls[1]["payload"]["messages"]))
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([call["status"] for call in trace], ["failed", "completed"])
            before = (output / "report.json").read_bytes()
            with self.assertRaises(local.RunFailure) as error:
                await local.run("Delta", output, base_url=url)
            self.assertEqual(error.exception.code, "output_exists")
            self.assertEqual((output / "report.json").read_bytes(), before)

    async def test_action_schema_refreshes_from_actual_graph_and_read_results(self):
        incomplete = abstention("riverwatch")
        incomplete["status"] = "insufficient_evidence"
        actions = [tool("entity_search", query="riverwatch"), tool("traverse_relationships", target="riverwatch", max_hops=3),
                   tool("read_evidence", evidence_id="memo-001"), tool("inspect_media", evidence_id="media/riverwatch-board.png"),
                   finish(incomplete), incomplete]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))

            def branches(index):
                return {b["properties"]["action"]["const"]: b for b in calls[index]["payload"]["response_format"]["schema"]["oneOf"]}

            self.assertNotIn("read_evidence", branches(0))
            self.assertNotIn("read_evidence", branches(1))
            graph_schema = branches(2)
            self.assertEqual(set(graph_schema["read_evidence"]["properties"]["arguments"]["properties"]["evidence_id"]["enum"]), {"memo-001", "memo-003"})
            self.assertEqual(set(graph_schema["finish"]["properties"]), {"action", "arguments"})
            citations = calls[-1]["payload"]["response_format"]["schema"]["properties"]["findings"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
            self.assertEqual(citations, ["memo-001"])
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["retrieved_evidence_ids"], ["memo-001"])
            self.assertIn("schema_policy", metadata)
            self.assertEqual(metadata["scope_rejections"][0]["action"], "inspect_media")
            self.assertEqual([call["name"] for call in json.loads((output / "tool-trace.json").read_text())],
                             ["entity_search", "traverse_relationships", "read_evidence"])

    async def test_successful_reads_do_not_repeat_and_only_available_media_can_be_read(self):
        incomplete = abstention("riverwatch")
        incomplete.update(status="insufficient_evidence", summary="Test stopped before a full investigation.")
        actions = [tool("search_evidence", entity_ids=["riverwatch", "silt_sensors"]),
                   tool("read_evidence", evidence_id="memo-001"), tool("read_evidence", evidence_id="memo-001"),
                   tool("inspect_media", evidence_id="img-note-002"), tool("read_media", evidence_id="img-note-002"),
                   tool("inspect_media", evidence_id="img-note-001"), tool("inspect_media", evidence_id="img-note-001"),
                   tool("read_media", evidence_id="img-note-001"), tool("read_media", evidence_id="img-note-001", timestamps=[14]),
                   finish(incomplete), incomplete]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))

            def choices(index, name):
                branches = calls[index]["payload"]["response_format"]["schema"]["oneOf"]
                match = next((b for b in branches if b["properties"]["action"]["const"] == name), None)
                return None if match is None else match["properties"]["arguments"]["properties"]["evidence_id"]["enum"]

            self.assertIsNone(choices(0, "read_evidence"))
            self.assertEqual(set(choices(1, "inspect_media")), {"img-note-001", "img-note-002", "video-tx-001"})
            self.assertNotIn("memo-001", choices(2, "read_evidence"))
            self.assertIsNone(choices(4, "read_media"))  # actual inspect_media said missing
            self.assertNotIn("img-note-002", choices(4, "inspect_media"))
            self.assertEqual(choices(6, "read_media"), ["img-note-001"])
            self.assertNotIn("img-note-001", choices(6, "inspect_media"))
            self.assertIsNone(choices(8, "read_media"))  # successful pixels retained
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["source_progress"]["available_media"], ["img-note-001"])
            self.assertEqual(metadata["source_progress"]["read_media"], ["img-note-001"])
            self.assertEqual(len(metadata["scope_rejections"]), 4)
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([call["name"] for call in trace], ["search_evidence", "read_evidence", "inspect_media", "inspect_media", "read_media"])
            self.assertIn("image_url", json.dumps(calls[8]["payload"]["messages"]))

    async def test_actual_video_reads_accept_new_and_mixed_offsets_block_default_alias_repeats(self):
        from media_tools import inspect_media

        workspace = local.Workspace(local.reports.DATA)
        try:
            suggestions = inspect_media(workspace, "video-tx-001")["suggested_timestamps"]
        finally:
            workspace.close()
        incomplete = abstention("riverwatch")
        incomplete.update(status="insufficient_evidence", summary="Test stopped before a full investigation.")
        actions = [tool("search_evidence", entity_ids=["riverwatch"]),
                   tool("inspect_media", evidence_id="video-tx-001"),
                   tool("read_media", evidence_id="video-tx-001", timestamps=[0]),
                   tool("read_media", evidence_id="video-tx-001", timestamps=[14]),
                   tool("read_media", evidence_id="video-tx-001", timestamps=[0]),
                   tool("read_media", evidence_id="video-tx-001", timestamps=[0, 27]),
                   tool("read_media", evidence_id="video-tx-001"),
                   tool("read_media", evidence_id="video-tx-001", timestamps=suggestions),
                   tool("read_media", evidence_id="video-tx-001", timestamps=None),
                   finish(incomplete), incomplete]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            state = metadata["media_progress"]["video-tx-001"]
            self.assertEqual(state["suggested_timestamps"], suggestions)
            self.assertEqual(state["successful_requested_offsets"], sorted({0, 14, 27, *suggestions}))
            self.assertEqual([sample["requested_seek_seconds"] for sample in state["samples"]], [0, 14, 0, 27, *suggestions])
            self.assertEqual([sample["source_timestamp_seconds"] for sample in state["samples"][:4]], [0, 14, 0, 27])
            self.assertTrue(all("source_pts" in sample and "source_time_base" in sample for sample in state["samples"]))
            self.assertEqual(len(metadata["scope_rejections"]), 3)
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([call["args"]["timestamps"] for call in trace if call["name"] == "read_media"], [[0], [14], [0, 27], suggestions])
            self.assertTrue(all(call["status"] == "completed" for call in trace))
            self.assertIn("image_url", json.dumps(calls[-1]["payload"]["messages"]))

    async def test_unresolved_identity_blocks_content_without_inventing_mcp_call(self):
        actions = [tool("traverse_relationships", target="delta_team"), tool("entity_search", query="Delta"),
                   finish(abstention()), abstention()]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("Delta", Path(directory) / "run", base_url=url, max_steps=len(actions))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["scope_rejections"][0]["action"], "traverse_relationships")
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([call["name"] for call in trace], ["entity_search"])
            schema = calls[0]["payload"]["response_format"]["schema"]
            self.assertEqual({branch["properties"]["action"]["const"] for branch in schema["oneOf"]}, {"entity_search", "finish"})

    async def test_changed_dataset_prevents_report_save(self):
        actions = [tool("entity_search", query="Delta"), finish(abstention()), abstention()]
        original = local.reports.read_dataset_metadata()
        changed = {**original, "sha256": "changed"}
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, _):
            output = Path(directory) / "run"
            with patch.object(local.reports, "read_dataset_metadata", side_effect=[original, changed]):
                with self.assertRaises(local.RunFailure) as error:
                    await local.run("Delta", output, base_url=url, max_steps=len(actions))
            self.assertEqual(error.exception.code, "dataset_changed")
            self.assertFalse((output / "report.json").exists())

    async def test_step_limit_saves_failure_without_success_or_raw_content(self):
        with tempfile.TemporaryDirectory() as directory, model_server([tool("entity_search", query="Delta")]) as (url, _):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure):
                await local.run("Delta", output, base_url=url, max_steps=1)
            self.assertEqual(json.loads((output / "failure.json").read_text())["code"], "step_limit")
            self.assertEqual(len(json.loads((output / "tool-trace.json").read_text())), 1)
            self.assertFalse((output / "report.md").exists())
            self.assertNotIn("delta_team", (output / "tool-trace.json").read_text())


if __name__ == "__main__":
    unittest.main()
