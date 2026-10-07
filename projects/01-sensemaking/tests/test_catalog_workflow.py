"""Catalog discovery, actual-response inventory, and source-credit boundaries."""
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_agent as reports
from evidence_catalog import EvidenceCatalog
from sensemaking import Workspace

PROJECT = Path(__file__).resolve().parents[1]


def fixture(data):
    from PIL import Image
    nodes = [{"id": value, "name": value, "aliases": []}
             for value in ("root", "child", "peer", "outside", "registry")]
    edges = [{"source": "root", "target": "child", "relation": "contains", "evidence_ids": ["proof"]},
             {"source": "peer", "target": "outside", "relation": "supplied_by", "evidence_ids": ["hidden"]}]
    (data / "graph.json").write_text(json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8")
    (data / "records.csv").write_text("id,entity_id,title,date,text,subject,predicate,value\n", encoding="utf-8")
    manifest = []
    for eid, ids in (("proof", ["registry"]), ("root-note", ["root"]), ("bridge", ["root", "peer"]),
                     ("peer-note", ["peer"]), ("hidden", ["outside"]), ("image", ["root"])):
        (data / (eid + ".txt")).write_text("Exact private source body " + eid, encoding="utf-8")
        record = {"id": eid, "entity_ids": ids, "title": eid, "kind": "text", "date": "2026-01-01",
                  "path": eid + ".txt", "assertions": [], "provenance": {"id": "hidden"}}
        if eid == "image":
            record.update(kind="image_annotation", media_path="pixels.png")
        manifest.append(record)
    Image.new("RGB", (4, 4), (30, 40, 50)).save(data / "pixels.png")
    (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def event(name, args, body=None, *, result=None, success=True):
    if result is None:
        result = {"content": [{"type": "text", "text": json.dumps(body)}], "structuredContent": body}
    return json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "sensemaking",
        "tool": name, "arguments": args, "status": "completed" if success else "failed", "result": result}})


class CatalogWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name)
        fixture(self.data)
        self.workspace = Workspace(self.data)
        self.addCleanup(self.workspace.close)
        self.catalog = EvidenceCatalog(self.data)
        self.addCleanup(self.catalog.close)
        self.evidence = {row["id"]: row for row in self.workspace.search()}
        self.entity = event("entity_search", {"query": "root"}, {"matches": [self.workspace.resolve("root")]})
        self.graph = event("traverse_relationships", {"target": "root"}, self.workspace.graph("root"))

    def read(self, eid, **overrides):
        return event("read_evidence", {"evidence_id": eid}, {**self.evidence[eid], **overrides})

    def pages(self, ids=None, query="", max_items=2):
        calls, cursor = [], None
        while True:
            args = {"query": query, "entity_ids": ids, "max_items": max_items, "max_bytes": 8192, "cursor": cursor}
            body = self.catalog.page(query, ids, max_items=max_items, cursor=cursor)
            calls.append(event("catalog_evidence", args, body))
            cursor = body["next_cursor"]
            if cursor is None:
                return calls

    def coverage(self, calls):
        return reports.collect_coverage("\n".join(calls), "root", data_dir=self.data, retrieval_profile="catalog")

    def validate(self, calls, citations=("proof",), actual_records=None):
        stream = "\n".join(calls)
        trace, retrieved, media = reports.collect_audit(stream, set(self.evidence), retrieval_profile="catalog")
        records = reports.collect_actual_records(stream, retrieval_profile="catalog") if actual_records is None else actual_records
        report = {"status": "complete", "target": "root", "findings": [{"evidence_ids": list(citations)}],
                  "conflicts": [], "media_observations": []}
        with patch.object(Workspace, "search", side_effect=AssertionError("No search replay")):
            reports.validate_workflow(report, trace, self.evidence, set(), media, self.data,
                coverage=self.saved_coverage,
                actual_records=records, retrieval_profile="catalog")
        return retrieved

    def test_profiles_preserve_default_contract_and_explicit_command(self):
        expected = {"entity_search", "traverse_relationships", "search_evidence", "read_evidence", "inspect_media", "read_media"}
        self.assertEqual(set(reports.TOOL_ARGS), expected)
        self.assertEqual(set(reports.tools_for_profile()), expected)
        self.assertEqual(set(reports.tools_for_profile("catalog")), expected - {"search_evidence"} | {"catalog_evidence"})
        tools = reports.tools_for_profile()
        tools["read_evidence"].clear()
        self.assertEqual(reports.TOOL_ARGS["read_evidence"], {"evidence_id"})
        self.assertEqual(reports.build_prompt("root"), reports.build_prompt("root", retrieval_profile="legacy"))
        self.assertNotIn("CATALOG RETRIEVAL", reports.build_prompt("root"))
        self.assertIn("Metadata cannot establish", reports.build_prompt("root", retrieval_profile="catalog"))
        command = reports.build_command("codex", Path("report.json"), self.data, retrieval_profile="catalog")
        args = json.loads(next(value.split("=", 1)[1] for value in command if value.startswith("mcp_servers.sensemaking.args=")))
        self.assertEqual(args[-2:], ["--retrieval-profile", "catalog"])
        with self.assertRaises(ValueError):
            reports.tools_for_profile("automatic")

    def test_complete_metadata_chain_credits_inventory_not_sources_or_edge_proof(self):
        calls = [self.entity, self.graph, *self.pages(["root", "child"])]
        trace, retrieved, media = reports.collect_audit("\n".join(calls), set(self.evidence), retrieval_profile="catalog")
        self.assertFalse(retrieved)
        self.assertFalse(media)
        coverage = self.coverage(calls)
        self.assertEqual(coverage["inventoried_entity_ids"], ["child", "root"])
        self.assertEqual(coverage["missing_proof_ids"], ["proof"])
        self.assertEqual(coverage["catalog_receipts"][0]["call_indices"], [3, 4])
        self.assertNotIn("private source", json.dumps(coverage))
        calls.append(self.read("proof"))
        self.saved_coverage = self.coverage(calls)
        self.assertTrue(self.saved_coverage["complete"])
        self.assertEqual(self.validate(calls), {"proof"})

    def test_nested_ids_metadata_snippets_and_mismatched_envelopes_never_cite(self):
        bodies = [{"id": "proof"}, {**self.evidence["proof"], "metadata_only": True},
                  {**self.evidence["proof"], "truncated": True}, self.evidence["hidden"]]
        for body in bodies:
            call = event("read_evidence", {"evidence_id": "proof"}, body)
            _, retrieved, _ = reports.collect_audit(call, set(self.evidence), retrieval_profile="catalog")
            self.assertEqual(retrieved, set())
            self.assertEqual(reports.collect_actual_records(call, retrieval_profile="catalog"), [])
        _, retrieved, _ = reports.collect_audit(self.read("root-note"), set(self.evidence), retrieval_profile="catalog")
        self.assertEqual(retrieved, {"root-note"})  # provenance.id='hidden' is not a source read.

    def test_media_needs_matching_header_and_actual_pixel_blocks_without_proof_credit(self):
        header = {"evidence_id": "image", "media_path": "pixels.png", "nested": {"id": "hidden"},
                  "provenance": "source prose: sampled source frame at 99 seconds"}
        text = {"type": "text", "text": json.dumps(header)}
        image = {"type": "image", "data": "aW1hZ2U=", "mimeType": "image/png"}
        call = event("read_media", {"evidence_id": "image"}, result={"content": [text, image]})
        _, retrieved, media = reports.collect_audit(call, set(self.evidence), retrieval_profile="catalog")
        self.assertEqual(retrieved, {"image"})
        self.assertEqual(media, {"image": {"image"}})
        self.assertEqual(reports.collect_actual_records(call, retrieval_profile="catalog"), [])
        for args, blocks in (({"evidence_id": "proof"}, [text, image]), ({"evidence_id": "image"}, [text])):
            _, retrieved, media = reports.collect_audit(event("read_media", args, result={"content": blocks}),
                                                       set(self.evidence), retrieval_profile="catalog")
            self.assertFalse(retrieved)
            self.assertFalse(media)
        video_header = {"evidence_id": "image", "media_path": "source.mp4",
                        "samples": [{"requested_seek_seconds": 14.5, "source_timestamp_seconds": 15.0}]}
        result = {"content": [{"type": "text", "text": json.dumps(video_header)}, image]}
        _, _, media = reports.collect_audit(event("read_media", {"evidence_id": "image"}, result=result),
                                           set(self.evidence), retrieval_profile="catalog")
        self.assertEqual(media, {"image": {15.0}})

    def test_partial_skipped_replayed_failed_and_filtered_chains_cannot_inventory(self):
        pages = self.pages(None, max_items=2)
        failed = json.loads(pages[1]); failed["item"]["status"] = "failed"
        attempts = [[pages[0]], [pages[-1]], [pages[0], pages[0], *pages[2:]],
                    [pages[0], pages[1], pages[1], pages[2]], [pages[0], json.dumps(failed), pages[-1]],
                    self.pages(None, query="Exact", max_items=2)]
        for attempt in attempts:
            with self.subTest(calls=len(attempt)):
                coverage = self.coverage([self.graph, *attempt, self.read("proof")])
                self.assertEqual(coverage["inventoried_entity_ids"], [])
                self.assertFalse(coverage["complete"])

    def test_empty_scope_differs_from_global_and_empty_entities_can_be_inventoried(self):
        empty = self.coverage([self.graph, *self.pages([]), self.read("proof")])
        self.assertEqual(empty["catalog_receipts"][0]["item_count"], 0)
        self.assertFalse(empty["complete"])
        batched = self.coverage([self.graph, *self.pages(["root"]), *self.pages(["child"]), self.read("proof")])
        self.assertTrue(batched["complete"])
        self.assertEqual(batched["catalog_receipts"][1]["item_count"], 0)
        self.assertTrue(self.coverage([self.graph, *self.pages(None), self.read("proof")])["complete"])

    def test_tampered_page_and_stale_snapshot_fail_without_inventory(self):
        calls = self.pages(None)
        item = json.loads(calls[-1])
        item["item"]["result"]["structuredContent"]["items"] = []
        coverage = self.coverage([self.graph, *calls[:-1], json.dumps(item), self.read("proof")])
        self.assertFalse(coverage["complete"])
        self.assertFalse(coverage["catalog_receipts"])
        (self.data / "root-note.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.coverage([self.graph, *calls])

    def test_exact_record_versions_retained_and_injected_unseen_body_rejected(self):
        calls = [self.entity, self.graph, *self.pages(None), self.read("proof"), self.read("root-note"),
                 self.read("root-note"), self.read("root-note", text="Different actually returned version")]
        records = reports.collect_actual_records("\n".join(calls), retrieval_profile="catalog")
        self.assertEqual(len(records), 3)
        self.assertEqual([record["text"] for record in records if record["id"] == "root-note"],
                         [self.evidence["root-note"]["text"], "Different actually returned version"])
        self.saved_coverage = self.coverage(calls)
        self.validate(calls, actual_records=records)
        with self.assertRaisesRegex(ValueError, "exact actual record versions"):
            self.validate(calls, actual_records=records + [self.evidence["bridge"]])

    def test_catalog_comentions_do_not_seed_scope_but_full_actual_source_does(self):
        peer_graph = event("traverse_relationships", {"target": "peer"}, self.workspace.graph("peer"))
        calls = [self.entity, self.graph, *self.pages(None), peer_graph, self.read("proof"), self.read("peer-note")]
        self.saved_coverage = self.coverage(calls)
        self.assertNotIn("peer", self.saved_coverage["connected_entity_ids"])
        self.assertEqual(len(self.saved_coverage["traversals"]), 1)
        with self.assertRaisesRegex(ValueError, "outside the connected"):
            self.validate(calls, citations=("peer-note",))
        calls += [self.read("bridge"), peer_graph, self.read("hidden")]
        self.saved_coverage = self.coverage(calls)
        self.assertEqual(len(self.saved_coverage["traversals"]), 2)
        self.assertTrue(self.saved_coverage["complete"])
        self.validate(calls, citations=("peer-note", "hidden"))

    def test_abstention_does_not_fabricate_completion_and_wrong_profile_rejected(self):
        reports.validate_workflow({"status": "insufficient_evidence"}, [], {}, set(), {}, self.data,
                                  retrieval_profile="catalog")
        with self.assertRaisesRegex(ValueError, "unexpected MCP tool"):
            reports.collect_audit(self.pages()[0], set(self.evidence))
        with self.assertRaisesRegex(ValueError, "unexpected MCP tool"):
            reports.collect_audit(event("search_evidence", {}, {"evidence": []}), set(self.evidence), retrieval_profile="catalog")

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Install requirements.txt for server construction")
    def test_mutation_between_catalog_and_tool_workspace_load_is_rejected(self):
        import mcp_server
        def changing_workspace(path):
            workspace = Workspace(path)
            (path / "root-note.txt").write_text("Mutated between catalog and tool loads", encoding="utf-8")
            return workspace
        with patch.object(mcp_server, "Workspace", side_effect=changing_workspace):
            with self.assertRaisesRegex(ValueError, "Dataset changed"):
                mcp_server.create_server(self.data, retrieval_profile="catalog")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install requirements.txt for actual stdio verification")
class CatalogTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_loaded_server_refuses_cached_record_after_dataset_mutation(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile(mode="w+") as errlog:
            data = Path(directory); fixture(data)
            params = StdioServerParameters(command=sys.executable, args=[str(PROJECT / "mcp_server.py"),
                "--data-dir", str(data), "--retrieval-profile", "catalog"])
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    (data / "root-note.txt").write_text("Changed during active session", encoding="utf-8")
                    failed = await client.call_tool("read_evidence", {"evidence_id": "proof"})
                    self.assertTrue(failed.isError)
                    self.assertIn("Dataset changed", str(failed.content))

    async def test_real_stdio_catalog_inventory_selective_reads_and_pixels(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile(mode="w+") as errlog:
            data = Path(directory); fixture(data)
            params = StdioServerParameters(command=sys.executable, args=[str(PROJECT / "mcp_server.py"),
                "--data-dir", str(data), "--retrieval-profile", "catalog"])
            calls = []
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    self.assertEqual({tool.name for tool in (await client.list_tools()).tools}, set(reports.tools_for_profile("catalog")))
                    for name, args in (("entity_search", {"query": "root"}), ("traverse_relationships", {"target": "root"})):
                        result = (await client.call_tool(name, args)).model_dump(exclude_none=True)
                        calls.append(event(name, args, result=result))
                    cursor = None
                    while True:
                        args = {"entity_ids": ["root", "child"], "max_items": 2, "cursor": cursor}
                        result = (await client.call_tool("catalog_evidence", args)).model_dump(exclude_none=True)
                        self.assertFalse(result.get("isError"))
                        body = result["structuredContent"]
                        self.assertTrue(body["metadata_only"])
                        self.assertTrue(all("text" not in row for row in body["items"]))
                        calls.append(event("catalog_evidence", args, result=result))
                        cursor = body["next_cursor"]
                        if cursor is None:
                            break
                    for name, eid in (("read_evidence", "proof"), ("read_media", "image")):
                        result = (await client.call_tool(name, {"evidence_id": eid})).model_dump(exclude_none=True)
                        self.assertFalse(result.get("isError"))
                        calls.append(event(name, {"evidence_id": eid}, result=result))
                    self.assertTrue((await client.call_tool("search_evidence", {})).isError)
            stream = "\n".join(calls)
            _, retrieved, media = reports.collect_audit(stream, {"proof", "image", "hidden"}, retrieval_profile="catalog")
            self.assertEqual(retrieved, {"proof", "image"})
            self.assertEqual(media, {"image": {"image"}})
            coverage = reports.collect_coverage(stream, "root", data_dir=data, retrieval_profile="catalog")
            reports.validate_coverage(coverage, "root", retrieval_profile="catalog")
            self.assertEqual(coverage["retrieved_record_ids"], ["proof"])


if __name__ == "__main__":
    unittest.main()
