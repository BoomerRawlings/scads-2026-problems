"""Opt-in report-context compaction retains exact returned evidence, not summaries."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_agent import HAS_MCP, finish, model_server, tool
from test_grounded_media import constrained_report, observations, partial_report
if HAS_MCP:
    import local_agent as local


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def record(eid, text="Exact evidence: naïve café\n  preserve spacing."):
    return {"id": eid, "kind": "text", "entity_ids": ["org-青"], "source": f"records/{eid}.txt",
            "title": "A dated source", "date": "2034-08-19", "text": text,
            "assertions": [{"subject": "org-青", "predicate": "readiness", "value": "uncertain"}],
            "extra_provenance": {"revision": "unusual-revision", "qualifier": ["do not flatten this"]}}


def event(name, args, body, *, structured=False, is_error=False, status="completed", server="sensemaking", extra_content=None):
    result = {"content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}] + (extra_content or []),
              "isError": is_error}
    if structured:
        result["structuredContent"] = copy.deepcopy(body)
    return {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": server, "tool": name,
            "arguments": args, "status": status, "error": None, "result": result}}


def facts():
    return {"policy": "current-run-provenance-v1", "scope_entity_ids": ["org-青"],
            "inventoried_scope_entity_ids": ["org-青"], "retrieved_source_ids": ["record-A", "record-B"],
            "media": [{"evidence_id": "record-B", "attachment_declared": True, "inspected_available": True,
                       "returned_pixel_locators": ["image"]}], "audio_processed": False, "video_coverage": "none"}


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class CompactEvidenceTests(unittest.TestCase):
    def build(self, events, validation_reasons=None):
        current = facts()
        isolated = observations({"evidence_id": "record-B", "locator": "image"})["media_observations"]
        isolated[0]["observation"] = "EXACT_ISOLATED_MODEL_OUTPUT: visible wording remains qualified."
        dataset = {"id": "arbitrary-corpus", "kind": "synthetic", "license": {"note": "exact dataset descriptor"}}
        constraints = local.grounded_report_constraints(current, dataset, isolated)
        schema = local.report_output_schema({"status": "insufficient_evidence", "target": "org-青"},
                                            {"record-A", "record-B"}, media_reads={"record-B": {"image"}},
                                            grounded_constraints=constraints)
        before = copy.deepcopy(events)
        with patch.object(local, "Workspace", side_effect=AssertionError("Never query the corpus during compaction")):
            messages, metadata = local.compact_synthesis_messages(events, "QUESTION_EXACT: what changed?", "org-青", dataset,
                                                                 schema, validation_reasons, current_facts=current,
                                                                 isolated_observations=isolated)
        self.assertEqual(events, before)
        self.assertEqual(sum(message["role"] == "system" for message in messages), 1)
        self.assertFalse(any(message["role"] == "assistant" for message in messages))
        self.assertEqual(json.loads(messages[1]["content"]), {
            "question": "QUESTION_EXACT: what changed?", "target": "org-青", "dataset": dataset,
            "accepted_finish": {"status": "insufficient_evidence", "target": "org-青"}})
        packet = json.loads(messages[2]["content"])
        self.assertEqual(packet["CURRENT_RUN_FACTS"], current)
        self.assertEqual(packet["FIXED_REPORT_FIELDS"], constraints)
        self.assertEqual(packet["FIXED_REPORT_FIELDS"]["media_observations"], isolated)
        self.assertEqual(metadata["policy"], "exact-record-compact-synthesis-v1")
        self.assertEqual(metadata["input_scope"], "canonical_report_messages_only")
        self.assertEqual(metadata["input_sha256"], hashlib.sha256(canonical(messages)).hexdigest())
        self.assertEqual(metadata["input_bytes"], len(canonical(messages)))
        return messages, metadata, packet

    def test_exact_records_dedupe_identical_bytes_preserve_versions_and_actual_call_lineage(self):
        first, second = record("record-A"), record("record-B", "SECOND_FULL_RECORD")
        changed = {**copy.deepcopy(first), "date": "2034-09-20", "text": "CHANGED_VERSION_MUST_REMAIN"}
        identity = {"matches": [{"id": "org-青", "name": "Arbitrary identity", "aliases": ["alias"]}]}
        graph = {"target": {"id": "org-青"}, "node_ids": ["org-青", "dependency"], "max_hops": 1,
                 "edges": [{"source": "org-青", "target": "dependency", "relation": "supplied_by", "evidence_ids": ["record-A"]}]}
        error_body = {"error": "EXACT_TOOL_ERROR: no source in requested scope", "attempted_id": "not-returned"}
        error = event("read_evidence", {"evidence_id": "not-returned"}, error_body, is_error=True,
                      extra_content=[{"type": "image", "mimeType": "image/png", "data": "ERROR_RAW_PIXELS"}])
        events = [event("entity_search", {"query": "alias"}, identity, structured=True),
                  event("traverse_relationships", {"target": "org-青", "max_hops": 1}, graph),
                  event("search_evidence", {"query": "SEARCH_ENVELOPE_NOT_RECORD"}, {"query": "SEARCH_ENVELOPE_NOT_RECORD", "evidence": [first, second]}, structured=True),
                  event("read_evidence", {"evidence_id": "record-A"}, dict(reversed(list(first.items())))),
                  event("read_evidence", {"evidence_id": "record-A"}, changed),
                  event("search_evidence", {}, {"query": "", "evidence": [changed]}),
                  event("inspect_media", {"evidence_id": "record-B"}, {"evidence_id": "record-B", "available": True,
                        "extraction": record("unseen", "INSPECTION_NESTED_RECORD_IS_NOT_RETRIEVAL")}),
                  event("read_media", {"evidence_id": "record-B"}, {"evidence_id": "record-B", "media_path": "private.png"},
                        extra_content=[{"type": "image", "mimeType": "image/png", "data": "SUCCESS_RAW_PIXELS"}]), error]
        messages, metadata, packet = self.build(events)
        self.assertEqual(packet["EVIDENCE_RECORDS"], [first, second, changed])
        self.assertEqual(packet["IDENTITY_AND_GRAPH_RESULTS"], [
            {"tool": "entity_search", "arguments": {"query": "alias"}, "result": identity},
            {"tool": "traverse_relationships", "arguments": {"target": "org-青", "max_hops": 1}, "result": graph}])
        expected_error = copy.deepcopy(error["item"]["result"])
        expected_error["content"] = expected_error["content"][:1]
        self.assertEqual(packet["TOOL_FAILURES"], [{"tool": "read_evidence", "arguments": {"evidence_id": "not-returned"}, "result": expected_error}])
        self.assertEqual(metadata["counts"], {"mcp_calls": 9, "evidence_records": 3, "evidence_occurrences": 5,
                         "duplicate_evidence_records": 2, "identity_graph_results": 2, "tool_failures": 1,
                         "omitted_raw_image_blocks": 2})
        self.assertEqual(metadata["evidence_lineage"], [
            {"record_index": 1, "evidence_id": "record-A", "sha256": hashlib.sha256(canonical(first)).hexdigest(), "calls": [3, 4]},
            {"record_index": 2, "evidence_id": "record-B", "sha256": hashlib.sha256(canonical(second)).hexdigest(), "calls": [3]},
            {"record_index": 3, "evidence_id": "record-A", "sha256": hashlib.sha256(canonical(changed)).hexdigest(), "calls": [5, 6]}])
        self.assertEqual([entry["calls"] for entry in metadata["identity_graph_lineage"]], [[1], [2]])
        self.assertEqual(metadata["error_calls"], [9])
        for excluded in ("SEARCH_ENVELOPE_NOT_RECORD", "INSPECTION_NESTED_RECORD_IS_NOT_RETRIEVAL", "SUCCESS_RAW_PIXELS", "ERROR_RAW_PIXELS", "private.png"):
            self.assertNotIn(excluded, json.dumps(messages))
        for excluded in (first["text"], changed["text"], "SECOND_FULL_RECORD", "EXACT_TOOL_ERROR", "EXACT_ISOLATED_MODEL_OUTPUT", "SUCCESS_RAW_PIXELS"):
            self.assertNotIn(excluded, json.dumps(metadata, ensure_ascii=False))

    def test_different_structured_and_text_envelope_versions_are_both_retained(self):
        first, revised = record("record-A"), record("record-A", "DIFFERENT_ACTUAL_TEXT_ENVELOPE_VERSION")
        result = event("search_evidence", {}, {"query": "", "evidence": [first]}, structured=True)
        result["item"]["result"]["content"][0]["text"] = json.dumps({"query": "", "evidence": [revised]})
        _, metadata, packet = self.build([result])
        self.assertEqual({canonical(item) for item in packet["EVIDENCE_RECORDS"]}, {canonical(first), canonical(revised)})
        self.assertEqual(metadata["counts"]["evidence_records"], 2)
        self.assertEqual(metadata["counts"]["evidence_occurrences"], 2)
        self.assertEqual([entry["calls"] for entry in metadata["evidence_lineage"]], [[1], [1]])

    def test_failed_records_stay_errors_and_partial_successes_fail_instead_of_silent_omission(self):
        complete = record("record-A")
        snippets = [{"id": "snippet", "text": "SNIPPET_NOT_FULL_SOURCE"},
                    {key: value for key, value in complete.items() if key != "source"},
                    {**complete, "truncated": True}]
        events = [event("read_evidence", {"evidence_id": "record-A"}, complete, status="failed"),
                  event("read_evidence", {"evidence_id": "record-A"}, complete, is_error=True)]
        _, metadata, packet = self.build(events)
        self.assertEqual(packet["EVIDENCE_RECORDS"], [])
        self.assertEqual(len(packet["TOOL_FAILURES"]), 2)
        self.assertEqual(metadata["error_calls"], [1, 2])
        self.assertEqual(metadata["counts"]["evidence_records"], 0)
        for snippet in snippets:
            with self.subTest(snippet=snippet), self.assertRaises(local.RunFailure) as caught:
                self.build([event("search_evidence", {}, {"evidence": [snippet]})])
            self.assertEqual(caught.exception.code, "compact_input_error")

    def test_duplicate_identity_graph_results_have_lineage_and_safe_feedback_is_retained(self):
        identity = {"matches": [{"id": "org-青"}]}
        call = event("entity_search", {"query": "alias"}, identity)
        messages, metadata, packet = self.build([call, copy.deepcopy(call)], ["Grounded field mismatch", "Grounded field mismatch"])
        self.assertEqual(len(packet["IDENTITY_AND_GRAPH_RESULTS"]), 1)
        self.assertEqual(metadata["identity_graph_lineage"][0]["calls"], [1, 2])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"].count("Grounded field mismatch"), 1)


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class CompactOptionTests(unittest.TestCase):
    def test_cli_defaults_off_and_opt_in_routes_both_required_flags(self):
        for flags, expected in (([], False), (["--grounded-media", "--compact-synthesis"], True)):
            runner = AsyncMock(return_value=Path("saved-output"))
            with self.subTest(flags=flags), patch.object(sys, "argv", ["local_agent.py", "riverwatch", *flags]), \
                    patch.object(local, "run", runner), redirect_stdout(io.StringIO()):
                self.assertEqual(local.main(), 0)
            self.assertEqual(runner.await_args.kwargs["compact_synthesis"], expected)
            self.assertEqual(runner.await_args.kwargs["grounded_media"], expected)

    def test_cli_rejects_a_value_after_the_boolean_flag(self):
        with patch.object(sys, "argv", ["local_agent.py", "riverwatch", "--grounded-media", "--compact-synthesis", "true"]), \
                patch.object(local, "run", AsyncMock()) as runner, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                local.main()
            self.assertEqual(caught.exception.code, 2)
            runner.assert_not_called()


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class CompactRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_requires_grounded_mode_and_boolean_before_http(self):
        requests = []
        with tempfile.TemporaryDirectory() as directory, model_server(on_request=lambda path, payload: requests.append(path)) as (url, calls):
            for index, (compact, grounded) in enumerate(((True, False), (1, True), ("true", True), (None, True))):
                with self.subTest(compact=compact, grounded=grounded), self.assertRaises(local.RunFailure):
                    await local.run("riverwatch", Path(directory) / f"invalid-{index}", base_url=url,
                                    compact_synthesis=compact, grounded_media=grounded)
            self.assertEqual(requests, [])
            self.assertEqual(calls, [])

    async def test_compaction_only_changes_report_context_planner_and_isolation_keep_pixels(self):
        report = partial_report()
        pair = {"evidence_id": "img-note-001", "locator": "image"}
        for compact in (False, True):
            def actions():
                yield tool("search_evidence", entity_ids=["riverwatch"])
                yield tool("inspect_media", evidence_id="img-note-001")
                yield tool("read_media", evidence_id="img-note-001")
                yield finish(report)
                yield observations(pair)
                yield constrained_report(calls[-1]["payload"]["response_format"]["schema"], report)

            with self.subTest(compact=compact), tempfile.TemporaryDirectory() as directory, model_server(actions()) as (url, calls):
                kwargs = {"compact_synthesis": True} if compact else {}
                output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=6, grounded_media=True, **kwargs)
                metadata = json.loads((output / "run-metadata.json").read_text())
                self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 4 + [1536, 3072])
                self.assertIn("image_url", json.dumps(calls[3]["payload"]["messages"]))
                self.assertIn("image_url", json.dumps(calls[4]["payload"]["messages"]))
                final_messages = calls[-1]["payload"]["messages"]
                if compact:
                    self.assertNotIn("image_url", json.dumps(final_messages))
                    self.assertNotIn("data:image/", json.dumps(final_messages))
                    self.assertNotIn("UNTRUSTED TOOL RESULT", json.dumps(final_messages))
                    packet = json.loads(final_messages[2]["content"])
                    returned_records = None
                    for message in calls[3]["payload"]["messages"]:
                        if not isinstance(message.get("content"), list):
                            continue
                        for block in message["content"]:
                            if block.get("type") != "text":
                                continue
                            try:
                                value = json.loads(block["text"])
                            except ValueError:
                                continue
                            if isinstance(value, dict) and "evidence" in value:
                                returned_records = value["evidence"]
                    self.assertIsNotNone(returned_records)
                    self.assertEqual(packet["EVIDENCE_RECORDS"], returned_records)
                    self.assertEqual(packet["FIXED_REPORT_FIELDS"]["media_observations"], observations(pair)["media_observations"])
                    compact_meta = metadata["compact_synthesis"]
                    self.assertTrue(compact_meta["enabled"])
                    self.assertEqual(len(compact_meta["generations"]), 1)
                    self.assertEqual(compact_meta["generations"][0]["input_sha256"], hashlib.sha256(canonical(final_messages)).hexdigest())
                    self.assertEqual(compact_meta["generations"][0]["counts"]["evidence_records"], len(returned_records))
                    self.assertEqual(compact_meta["generations"][0]["counts"]["omitted_raw_image_blocks"], 1)
                else:
                    self.assertIn("image_url", json.dumps(final_messages))
                    self.assertIn("UNTRUSTED TOOL RESULT", json.dumps(final_messages))
                    self.assertFalse(metadata["compact_synthesis"]["enabled"])
                    self.assertEqual(metadata["compact_synthesis"]["generations"], [])
                accepted = json.loads((output / "report.json").read_text())
                self.assertEqual(accepted["media_observations"], observations(pair)["media_observations"])
                self.assertEqual([item["name"] for item in json.loads((output / "tool-trace.json").read_text())],
                                 ["search_evidence", "inspect_media", "read_media"])


if __name__ == "__main__":
    unittest.main()
