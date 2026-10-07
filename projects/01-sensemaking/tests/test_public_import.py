"""Offline semantic/provenance checks against the pinned public capture."""

import copy
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import capture_public_data as capture
from scripts import import_public_data as importer
from sensemaking import Workspace


class PublicImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture_dir = capture.DEFAULT_OUTPUT
        cls.sources, cls.capture_bytes = importer.load_sources(cls.capture_dir)
        cls.files, cls.totals = importer.build_dataset(cls.sources, cls.capture_bytes)

    def test_deterministic_offline_import_and_byte_exact_sources(self):
        with tempfile.TemporaryDirectory() as temporary, patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network forbidden")):
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            importer.import_dataset(self.capture_dir, first)
            importer.import_dataset(self.capture_dir, second)
            left = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
            right = {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()}
            self.assertEqual(left, right)
            for source in self.sources:
                self.assertEqual((first / "sources" / source["entry"]["path"]).read_bytes(), source["raw"])
            self.assertEqual((first / "sources/capture-manifest.json").read_bytes(), self.capture_bytes)

    def test_real_workspace_namespaced_identity_search_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "imported"
            importer.import_dataset(self.capture_dir, output)
            workspace = Workspace(output)
            try:
                self.assertEqual(len(workspace.entities()), 12)
                with self.assertRaisesRegex(ValueError, "Ambiguous"):
                    workspace.resolve("National Cancer Institute")
                self.assertEqual(workspace.resolve("Q664846")["id"], "wikidata:q664846")
                graph = workspace.graph("ror:01cwqze88", 2)
                self.assertEqual(set(graph["node_ids"]), {"ror:01cwqze88", "ror:040gcmg81", "ror:05bjen692", "ror:03v6m3209", "ror:05n6zrm60", "ror:00vkwep27"})
                self.assertEqual(len(graph["edges"]), 5)
                self.assertTrue(all(len(edge["evidence_ids"]) == 2 for edge in graph["edges"]))
                # ROR related organizations and Wiki identities are not silently traversable children.
                self.assertNotIn("ror:02qyzaf42", graph["node_ids"])
                self.assertNotIn("wikidata:q664846", graph["node_ids"])
                self.assertEqual(workspace.graph("wikidata:q390551")["edges"], [])
                matches = workspace.search("qualified_claim_requires_scope_review", ["wikidata:q664846"])
                self.assertEqual([match["id"] for match in matches], ["claims-wikidata-Q664846"])
                source = workspace.read(matches[0]["id"])
                self.assertIn("Q664846$200BD237-C74D-44BF-A20A-8EF6B63C95E0", source["text"])
                self.assertEqual(source["assertions"], [])
                # A candidate mention permits evidence pivots without merging identities.
                self.assertIn("ror:040gcmg81", source["entity_ids"])
                negative = workspace.read("claims-wikidata-Q6973636")
                self.assertIn("ror:01cwqze88", negative["entity_ids"])
                self.assertIn("rejected_list_article_type", negative["text"])
            finally:
                workspace.close()

    def test_every_wikidata_statement_retained_and_classified(self):
        ledger = json.loads(self.files["projection-ledger.json"])
        decisions = ledger["decisions"]
        for source in self.sources:
            if source["spec"]["provider"] != "wikidata":
                continue
            qid = source["spec"]["entity_id"]
            extract = json.loads(self.files[f"evidence/wikidata-{qid}.json"])
            full = source["entity"]["claims"]
            indexed = extract["literal_source_extract"]["claims"]
            self.assertEqual(indexed, {prop: statements for prop, statements in full.items() if prop in importer.INDEXED_PROPERTIES})
            actual = [d for d in decisions if d["source_entity"] == importer.node_id("wikidata", qid)]
            self.assertEqual(len(actual), sum(map(len, full.values())))
            for prop, statements in full.items():
                for index, statement in enumerate(statements):
                    path = f"/entities/{qid}/claims/{prop}/{index}"
                    decision = next(d for d in actual if d["source_path"] == path)
                    self.assertEqual(decision["statement_guid"], statement["id"])
                    self.assertTrue(decision["exclusion_reasons"] or "projected_edge" in decision)
            self.assertEqual(extract["source_provenance"]["revision"], source["entry"]["revision"])
            self.assertEqual(extract["source_provenance"]["sha256"], hashlib.sha256(source["raw"]).hexdigest())
            self.assertEqual(extract["source_provenance"]["url"], source["spec"]["url"])

    def test_crosswalk_negative_not_merged_and_frontier_explicit(self):
        ledger = json.loads(self.files["projection-ledger.json"])
        pairs = {(x["ror"], x["wikidata"]): x for x in ledger["crosswalks"]}
        negative = pairs["ror:01cwqze88", "wikidata:q6973636"]
        self.assertEqual(negative["status"], "rejected_list_article_type")
        self.assertFalse(negative["merged"])
        self.assertEqual(pairs["ror:01cwqze88", "wikidata:q390551"]["status"], "reciprocal_candidate_requires_identity_review")
        self.assertEqual(pairs["ror:01ggx4157", "wikidata:q42944"]["status"], "endpoint_not_captured")
        self.assertTrue(all(not x["merged"] for x in pairs.values()))
        self.assertIn("ror:01ggx4157", ledger["frontier_entity_ids"])
        self.assertIn("wikidata:q476322", ledger["frontier_entity_ids"])
        graph = json.loads(self.files["graph.json"])
        self.assertEqual({edge["relation"] for edge in graph["edges"]}, {"contains"})
        self.assertTrue(all(edge["source"].startswith("ror:") and edge["target"].startswith("ror:") for edge in graph["edges"]))
        self.assertEqual(self.totals["projected_source_assertions"], 10)

    def test_qualified_deprecated_unknown_values_are_not_flattened(self):
        sources = copy.deepcopy(self.sources)
        nci = next(source for source in sources if source["spec"]["id"] == "wikidata-Q664846")
        base = copy.deepcopy(nci["entity"]["claims"]["P749"][0])
        base.pop("qualifiers", None)
        base.pop("qualifiers-order", None)
        for change, expected in [({}, True), ({"rank": "deprecated"}, False), ({"qualifiers": {"P582": [{"snaktype": "somevalue"}]}}, False)]:
            statement = copy.deepcopy(base)
            statement.update(change)
            nci["entity"]["claims"]["P749"] = [statement]
            files, _ = importer.build_dataset(sources, self.capture_bytes)
            graph = json.loads(files["graph.json"])
            self.assertEqual(any(edge["source"] == "wikidata:q390551" and edge["target"] == "wikidata:q664846" for edge in graph["edges"]), expected)
        for snaktype in ("somevalue", "novalue"):
            statement = copy.deepcopy(base)
            statement["mainsnak"] = {"property": "P749", "snaktype": snaktype}
            nci["entity"]["claims"]["P749"] = [statement]
            files, _ = importer.build_dataset(sources, self.capture_bytes)
            self.assertFalse(any(edge["source"].startswith("wikidata:") for edge in json.loads(files["graph.json"])["edges"]))
            extract = json.loads(files["evidence/wikidata-Q664846.json"])
            self.assertEqual(extract["literal_source_extract"]["claims"]["P749"][0], statement)

    def test_corrupt_hash_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "capture"
            source.mkdir()
            shutil.copytree(self.capture_dir / "raw", source / "raw")
            (source / "capture-manifest.json").write_bytes(self.capture_bytes)
            target = source / "raw/ror-040gcmg81.json"
            target.write_bytes(target.read_bytes() + b" ")
            output = Path(temporary) / "result"
            with self.assertRaisesRegex(ValueError, "hash_mismatch"):
                importer.import_dataset(source, output)
            self.assertFalse(output.exists())

    def test_wrong_pinned_revision_refused_even_with_new_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "capture"
            source.mkdir()
            shutil.copytree(self.capture_dir / "raw", source / "raw")
            manifest = json.loads(self.capture_bytes)
            entry = next(e for e in manifest["sources"] if e["id"] == "wikidata-Q664846")
            path = source / entry["path"]
            body = json.loads(path.read_bytes())
            body["entities"]["Q664846"]["lastrevid"] -= 1
            raw = importer.encoded(body)
            path.write_bytes(raw)
            entry.update(sha256=capture.digest(raw), size_bytes=len(raw))
            (source / "capture-manifest.json").write_bytes(importer.encoded(manifest))
            with self.assertRaisesRegex(ValueError, "pinned_revision_mismatch"):
                importer.import_dataset(source, Path(temporary) / "result")

    def test_manifest_change_during_verification_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "capture"
            source.mkdir()
            shutil.copytree(self.capture_dir / "raw", source / "raw")
            manifest_path = source / "capture-manifest.json"
            manifest_path.write_bytes(self.capture_bytes)
            original_verify = capture.verify_capture

            def mutate_after_verification(directory):
                result = original_verify(directory)
                manifest_path.write_bytes(self.capture_bytes + b" ")
                return result

            with patch.object(capture, "verify_capture", side_effect=mutate_after_verification):
                with self.assertRaisesRegex(ValueError, "manifest_changed"):
                    importer.import_dataset(source, Path(temporary) / "result")

    def test_foreign_and_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "foreign"
            output.mkdir()
            (output / "notes.txt").write_text("keep this", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "output_exists"):
                importer.import_dataset(self.capture_dir, output)
            self.assertEqual((output / "notes.txt").read_text(), "keep this")
            empty = Path(temporary) / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, "output_exists"):
                importer.import_dataset(self.capture_dir, empty)
            output2 = Path(temporary) / "ours"
            importer.import_dataset(self.capture_dir, output2)
            before = (output2 / "import-manifest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "output_exists"):
                importer.import_dataset(self.capture_dir, output2)
            self.assertEqual((output2 / "import-manifest.json").read_bytes(), before)

    def test_artifact_hash_manifest_and_index_boundaries(self):
        manifest = json.loads(self.files["import-manifest.json"])
        self.assertLess(sum(map(len, self.files.values())), importer.MAX_OUTPUT_BYTES)
        for artifact in manifest["files"]:
            raw = self.files[artifact["path"]]
            self.assertEqual(len(raw), artifact["size_bytes"])
            self.assertEqual(capture.digest(raw), artifact["sha256"])
        indexed = json.loads(self.files["manifest.json"])
        self.assertTrue(all(item["path"].startswith("evidence/") for item in indexed))
        self.assertEqual(len(indexed), 12)
        # Full multilingual entity JSON remains inspectable without entering search results.
        self.assertTrue(all(not item["path"].startswith("sources/") for item in indexed))


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install requirements.txt for public MCP transport verification")
class PublicImportMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_imported_source_through_real_mcp_transport(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from run_agent import collect_coverage, validate_workflow

        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryFile(mode="w+") as errlog:
            output = Path(temporary) / "imported"
            importer.import_dataset(capture.DEFAULT_OUTPUT, output)
            params = StdioServerParameters(command=sys.executable, args=[str(capture.PROJECT / "mcp_server.py"), "--data-dir", str(output)])
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    events = []

                    async def call(name, args):
                        result = await client.call_tool(name, args)
                        events.append({"type": "item.completed", "item": {
                            "type": "mcp_tool_call", "server": "sensemaking", "tool": name,
                            "arguments": args, "status": "completed",
                            "result": result.model_dump(mode="json", by_alias=True, exclude_none=True),
                        }})
                        return result

                    def coverage():
                        return collect_coverage("\n".join(json.dumps(event) for event in events), "ror:01cwqze88")

                    found = await call("entity_search", {"query": "National Cancer Institute"})
                    self.assertTrue(found.structuredContent["ambiguous"])
                    identity = await call("entity_search", {"query": "ror:01cwqze88"})
                    self.assertFalse(identity.isError)
                    graph = await call("traverse_relationships", {"target": "ror:01cwqze88", "max_hops": 2})
                    self.assertFalse(graph.isError)
                    self.assertEqual(len(graph.structuredContent["edges"]), 5)
                    empty = await call("search_evidence", {"entity_ids": []})
                    self.assertEqual(empty.structuredContent["evidence"], [])
                    counterpart = await call("read_evidence", {"evidence_id": "identity-wikidata-Q664846"})
                    self.assertFalse(counterpart.isError)
                    trace = [{"name": name, "args": args, "status": "completed"} for name, args in [
                        ("entity_search", {"query": "ror:01cwqze88"}),
                        ("traverse_relationships", {"target": "ror:01cwqze88", "max_hops": 2}),
                        ("search_evidence", {"entity_ids": []}),
                        ("read_evidence", {"evidence_id": "identity-wikidata-Q664846"}),
                    ]]
                    report = {"status": "complete", "target": "ror:01cwqze88", "findings": [{"evidence_ids": ["identity-wikidata-Q664846"]}],
                              "conflicts": [], "media_observations": []}
                    workspace = Workspace(output)
                    try:
                        evidence = {item["id"]: item for item in workspace.search()}
                    finally:
                        workspace.close()
                    with self.assertRaisesRegex(ValueError, "outside the connected"):
                        validate_workflow(report, trace, evidence, set(), {}, output, coverage=coverage())
                    candidate = await call("read_evidence", {"evidence_id": "claims-ror-040gcmg81"})
                    self.assertFalse(candidate.isError)
                    self.assertIn("wikidata:q664846", candidate.structuredContent["entity_ids"])
                    trace.append({"name": "read_evidence", "args": {"evidence_id": "claims-ror-040gcmg81"}, "status": "completed"})
                    inventory_args = {"query": "", "entity_ids": graph.structuredContent["node_ids"]}
                    inventory = await call("search_evidence", inventory_args)
                    self.assertFalse(inventory.isError)
                    trace.append({"name": "search_evidence", "args": inventory_args, "status": "completed"})
                    self.assertTrue(coverage()["complete"])
                    # An actual ROR source mention connects the separate Wiki identity without merging it.
                    validate_workflow(report, trace, evidence, set(), {}, output, coverage=coverage())
                    claims = await call("search_evidence", {"query": "P749", "entity_ids": ["wikidata:q664846"]})
                    self.assertFalse(claims.isError)
                    self.assertEqual([record["id"] for record in claims.structuredContent["evidence"]], ["claims-wikidata-Q664846"])
                    trace.append({"name": "search_evidence", "args": {"query": "P749", "entity_ids": ["wikidata:q664846"]}, "status": "completed"})
                    validate_workflow(report, trace, evidence, set(), {}, output, coverage=coverage())
                    record = await call("read_evidence", {"evidence_id": "claims-wikidata-Q6973636"})
                    self.assertFalse(record.isError)
                    self.assertIn("rejected_list_article_type", record.structuredContent["text"])
                    self.assertIn("ror:01cwqze88", record.structuredContent["entity_ids"])
                    media = await call("inspect_media", {"evidence_id": "claims-wikidata-Q664846"})
                    self.assertFalse(media.structuredContent["available"])


if __name__ == "__main__":
    unittest.main()
