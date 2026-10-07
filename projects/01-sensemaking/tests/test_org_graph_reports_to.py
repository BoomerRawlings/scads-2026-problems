"""Explicit sibling relation conformance; scripted transport, never model acceptance."""
import copy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import run_agent
from sensemaking import DATA, RELATIONS, Workspace
from scripts import import_org_graph as adapter
from tests.test_org_graph_import import package, pointer_value, write_files


def chain_package():
    """Separate authored test chain; never attributed to the real P4 backup."""
    source = package()
    snapshot = source["history"]["snapshots"][0]
    second = snapshot["assertions"][1]
    second.update(subject="chief/x~y", object="other", evidence_ids=["second-source"])
    # Preserve matrix status rather than silently constructing a primary forest.
    second_evidence = copy.deepcopy(snapshot["evidence"][0])
    second_evidence.update(id="second-source", source_ref="test://statement/02", message_ids=["message-02"],
                           text="Authored test claim: chief/x~y reports to other in a matrix role.")
    snapshot["evidence"].append(second_evidence)
    source["dataset"]["messages"].append({"id": "message-02", "source_ref": "test://message/02",
        "body": "Second authored source message, not an independent observation of real people."})
    return source


class ReportsToCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name)
        self.raw = adapter.encoded(chain_package())
        self.files, _ = adapter.build_dataset(self.raw, snapshot_id="chosen", activate_reports_to=True)
        write_files(self.data, self.files)
        self.workspace = Workspace(self.data)
        self.addCleanup(self.workspace.close)
        self.ids = {node["source_entity_id"]: node["id"] for node in self.workspace.entities()}

    def test_real_capability_directed_two_hop_types_and_no_reverse_edge(self):
        self.assertIn("reports_to", RELATIONS)
        a, b, c = (self.ids[key] for key in ("Worker", "chief/x~y", "other"))
        two = self.workspace.graph(a, 2)
        self.assertEqual(two["paths"][c], [a, b, c])
        self.assertEqual([edge["reporting_type"] for edge in two["edges"]], ["primary", "matrix"])
        self.assertEqual([edge["review_status"] for edge in two["edges"]], ["unreviewed", "unreviewed"])
        self.assertTrue(all("selected" not in edge for edge in two["edges"]))
        self.assertIn("employee to manager", two["scope_note"])
        self.assertIn("not selected-chart or verified current authority", two["scope_note"])
        self.assertEqual(set(self.workspace.graph(a, 1)["node_ids"]), {a, b})
        self.assertEqual(self.workspace.graph(a, 0)["edges"], [])
        self.assertEqual(self.workspace.graph(c, 3)["node_ids"], [c])

    def test_activation_changes_no_source_units_or_identity_provenance(self):
        inactive, _ = adapter.build_dataset(self.raw, snapshot_id="chosen")
        self.assertEqual(inactive["manifest.json"], self.files["manifest.json"])
        self.assertEqual(json.loads(inactive["graph.json"])["nodes"], self.workspace.entities())
        for name, body in inactive.items():
            if name.startswith(("sources/", "evidence/")):
                self.assertEqual(body, self.files[name])
        self.assertEqual(json.loads(inactive["graph.json"])["edges"], [])
        self.assertNotEqual(json.loads(inactive["dataset.json"])["id"], json.loads(self.files["dataset.json"])["id"])
        for edge in self.workspace.graph_data["edges"]:
            self.assertEqual(len(edge["evidence_ids"]), 3)
            for eid in edge["evidence_ids"]:
                record = self.workspace.read(eid)
                body = json.loads(record["text"])
                self.assertEqual(body["source_value"], pointer_value(json.loads(self.raw), body["source_provenance"]["json_pointer"]))
                self.assertEqual(body["source_provenance"]["sha256"], adapter.digest(self.raw))

    def test_legacy_dataset_scope_note_and_unknown_relation_rules_stay_exact(self):
        legacy = Workspace(DATA)
        try:
            note = "Directed contains / depends_on / supplied_by edges only. Path inclusion is relevance, not proof of an inherited property."
            self.assertTrue(all(legacy.graph(node["id"])["scope_note"] == note for node in legacy.entities()))
        finally:
            legacy.close()
        graph = json.loads(self.files["graph.json"])
        graph["edges"][0]["relation"] = "inferred_controls"
        (self.data / "graph.json").write_bytes(adapter.encoded(graph))
        with self.assertRaisesRegex(ValueError, "Unsupported relation"):
            Workspace(self.data)


@unittest.skipUnless(importlib.util.find_spec("mcp") is not None, "Install requirements.txt for real MCP transport")
class ReportsToMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_two_hop_catalog_proofs_must_be_fully_read(self):
        await self.exercise_package(chain_package(), "chosen", "Worker", expected_edges=2, expected_hops=2)

    async def exercise_package(self, source_package, snapshot_id, original_entity_id, *, expected_edges,
                               expected_hops, entity_ids=None, raw_bytes=None):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        raw = adapter.encoded(source_package) if raw_bytes is None else raw_bytes
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryFile(mode="w+") as errlog:
            root = Path(temporary)
            source, data = root / "source.json", root / "dataset"
            source.write_bytes(raw)
            adapter.import_package(source, data, snapshot_id=snapshot_id,
                                   entity_ids=entity_ids, activate_reports_to=True)
            local = Workspace(data)
            try:
                evidence = {record["id"]: record for record in local.search()}
            finally:
                local.close()
            events = []
            params = StdioServerParameters(command=sys.executable, args=[str(project / "mcp_server.py"),
                "--data-dir", str(data), "--retrieval-profile", "catalog"])
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as client:
                    await client.initialize()
                    self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                                     set(run_agent.tools_for_profile("catalog")))

                    async def call(name, args):
                        result = await client.call_tool(name, args)
                        self.assertFalse(result.isError, name)
                        events.append(json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call",
                            "server": "sensemaking", "tool": name, "arguments": args, "status": "completed",
                            "result": result.model_dump(mode="json", exclude_none=True)}}))
                        return result.structuredContent

                    found = await call("entity_search", {"query": original_entity_id})
                    targets = [node for node in found["matches"] if node["source_entity_id"] == original_entity_id]
                    self.assertEqual(len(targets), 1)
                    target = targets[0]["id"]
                    graph = await call("traverse_relationships", {"target": target, "max_hops": expected_hops})
                    self.assertEqual(len(graph["edges"]), expected_edges)
                    self.assertEqual(max(len(path) - 1 for path in graph["paths"].values()), expected_hops)
                    self.assertTrue(all(edge["relation"] == "reports_to" for edge in graph["edges"]))
                    self.assertIn("employee to manager", graph["scope_note"])
                    proofs = {eid for edge in graph["edges"] for eid in edge["evidence_ids"]}
                    cursor, pages, cards = None, 0, []
                    while True:
                        page = await call("catalog_evidence", {"query": "", "entity_ids": graph["node_ids"],
                            "max_items": 3, "max_bytes": 8192, "cursor": cursor})
                        self.assertTrue(page["metadata_only"])
                        self.assertFalse(page["evidence_content_returned"])
                        cards.extend(page["items"])
                        cursor = page["next_cursor"]
                        pages += 1
                        if cursor is None:
                            break
                        self.assertLess(pages, 12)
                    self.assertTrue(proofs <= {card["id"] for card in cards})

                    def collected():
                        stream = "\n".join(events)
                        coverage = run_agent.collect_coverage(stream, target, data_dir=data, retrieval_profile="catalog")
                        audit, retrieved, media = run_agent.collect_audit(stream, set(evidence), retrieval_profile="catalog")
                        records = run_agent.collect_actual_records(stream, retrieval_profile="catalog")
                        return coverage, audit, retrieved, media, records

                    coverage, _, retrieved, _, _ = collected()
                    self.assertEqual(retrieved, set())
                    self.assertEqual(set(coverage["required_proof_ids"]), proofs)
                    self.assertEqual(set(coverage["inventoried_entity_ids"]), set(graph["node_ids"]))
                    with self.assertRaisesRegex(ValueError, "retrieve full edge proof"):
                        run_agent.validate_coverage(coverage, target, retrieval_profile="catalog")

                    # Structural validation fixture only; no generated analytic product.
                    report = {"status": "complete", "target": target, "findings": [{"evidence_ids": sorted(proofs)}],
                              "conflicts": [], "media_observations": []}
                    for index, eid in enumerate(sorted(proofs)):
                        record = await call("read_evidence", {"evidence_id": eid})
                        body = json.loads(record["text"])
                        self.assertEqual(body["source_value"], pointer_value(source_package, body["source_provenance"]["json_pointer"]))
                        self.assertEqual(body["source_provenance"]["sha256"], adapter.digest(raw))
                        self.assertEqual(body["source_provenance"]["snapshot_id"], snapshot_id)
                        if body["record_type"] == "reporting_assertion":
                            self.assertEqual(body["source_value"]["review_status"], "unreviewed")
                            self.assertNotIn("selected", body["source_value"])
                        coverage, audit, retrieved, media, records = collected()
                        if index < len(proofs) - 1:
                            with self.assertRaisesRegex(ValueError, "retrieve full edge proof"):
                                run_agent.validate_workflow(report, audit, evidence, set(), media, data,
                                    coverage=coverage, actual_records=records, retrieval_profile="catalog")
                    run_agent.validate_workflow(report, audit, evidence, set(), media, data,
                        coverage=coverage, actual_records=records, retrieval_profile="catalog")
                    self.assertEqual(retrieved, proofs)
                    self.assertEqual(source.read_bytes(), raw)
                    return {"actual_calls": len(events), "active_edges": len(graph["edges"]), "max_hops": expected_hops,
                            "catalog_pages": pages, "full_proof_reads": len(proofs), "source_sha256": adapter.digest(raw)}


if __name__ == "__main__":
    unittest.main()
