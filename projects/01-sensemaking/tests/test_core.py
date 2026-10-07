"""Behavioral checks independent of the showcase fixture's authored oracle.

Run: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from sensemaking import Workspace, evaluate


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.graph = {
            "nodes": [
                {"id": "org", "name": "Example Organization", "aliases": ["HQ"]},
                {"id": "lab", "name": "Aster", "aliases": ["Research Lab"]},
                {"id": "service", "name": "Compute Service", "aliases": ["Shared"]},
                {"id": "supplier", "name": "Cooling Supplier", "aliases": ["Shared"]},
                {"id": "annex", "name": "Aster Annex", "aliases": []},
                {"id": "external", "name": "Contract Registry", "aliases": []},
            ],
            "edges": [
                {"source": "org", "target": "lab", "relation": "contains", "evidence_ids": ["e-org"]},
                {"source": "lab", "target": "service", "relation": "depends_on", "evidence_ids": ["e-contract"]},
                {"source": "service", "target": "supplier", "relation": "supplied_by", "evidence_ids": ["e-contract"]},
            ],
        }
        (self.data / "graph.json").write_text(json.dumps(self.graph), encoding="utf-8")
        columns = ["id", "entity_id", "title", "date", "text", "subject", "predicate", "value"]
        with (self.data / "records.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerow(dict(zip(columns, ["e-register", "service", "Service status register", "2026-06-01", "Compute Service was listed as operational.", "service", "operational_status", "operational"])))
        documents = [
            ("e-org", "org", "document", "Organization chart", "2026-06-01", "Example Organization contains Aster.", []),
            ("e-contract", "external", "document", "Dependency contract", "2026-06-01", "Aster depends on Compute Service; Compute Service is supplied by Cooling Supplier.", []),
            ("e-note", "service", "document", "Service operator note", "2026-06-02", "Compute Service was reported as unavailable; this report requires verification.", [{"subject": "service", "predicate": "operational_status", "value": "unavailable"}]),
            ("e-image", "supplier", "image", "Supplier image annotation", "2026-06-02", "Authored annotation: cooling alarm visible.", []),
            ("e-video", "lab", "video", "Lab video transcript", "2026-06-02", "Authored transcript: lab staff discuss capacity planning.", []),
            ("e-annex", "annex", "document", "Aster Annex notice", "2026-06-02", "Aster Annex is unrelated to the laboratory investigation.", []),
        ]
        manifest = []
        for evidence_id, entity_id, kind, title, date, text, assertions in documents:
            relative = f"{evidence_id}.txt"
            (self.data / relative).write_text(text, encoding="utf-8")
            manifest.append({"id": evidence_id, "entity_ids": [entity_id], "kind": kind, "title": title, "date": date, "path": relative, "assertions": assertions, "extraction": "authored_test_fixture"})
        (self.data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.workspace = Workspace(self.data)
        self.addCleanup(self.workspace.close)

    def test_exact_alias_normalization_and_ambiguity(self):
        self.assertEqual(self.workspace.resolve("  rEsEaRcH lAb  ")["id"], "lab")
        self.assertEqual(self.workspace.resolve("Aster")["id"], "lab")
        self.assertEqual(self.workspace.resolve("Aster Annex")["id"], "annex")
        with self.assertRaisesRegex(ValueError, "Ambiguous.*service.*supplier"):
            self.workspace.resolve("Shared")
        for invalid in ("", "Aste", "not an entity"):
            with self.subTest(query=invalid), self.assertRaises(ValueError):
                self.workspace.resolve(invalid)

    def test_directed_traversal_respects_depth_and_retains_provenance(self):
        expected = {
            0: {"org"},
            1: {"org", "lab"},
            2: {"org", "lab", "service"},
            3: {"org", "lab", "service", "supplier"},
        }
        for depth, ids in expected.items():
            with self.subTest(depth=depth):
                result = self.workspace.graph("HQ", depth)
                self.assertEqual(set(result["node_ids"]), ids)
                self.assertTrue(all(len(path) - 1 <= depth for path in result["paths"].values()))
                self.assertEqual(len(result["edges"]), depth)
                for edge in result["edges"]:
                    self.assertIn(edge, self.graph["edges"])
                    for citation in edge["evidence_ids"]:
                        self.assertEqual(self.workspace.read(citation)["id"], citation)
        self.assertEqual(self.workspace.graph("org", 3)["paths"]["supplier"], ["org", "lab", "service", "supplier"])
        self.assertEqual(self.workspace.graph("supplier", 10)["node_ids"], ["supplier"])

    def test_cycle_terminates_without_duplicating_nodes(self):
        self.graph["edges"].append({"source": "supplier", "target": "lab", "relation": "depends_on", "evidence_ids": ["e-contract"]})
        (self.data / "graph.json").write_text(json.dumps(self.graph), encoding="utf-8")
        cyclic = Workspace(self.data)
        self.addCleanup(cyclic.close)
        result = cyclic.graph("org", 10)
        self.assertEqual(result["node_ids"], ["org", "lab", "service", "supplier"])
        self.assertEqual(len(result["edges"]), 4)
        self.assertEqual(result["paths"]["lab"], ["org", "lab"])

    def test_invalid_targets_depths_and_ids_are_rejected(self):
        for depth in (-1, 11, 1.5, "2", True):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                self.workspace.graph("org", depth)
        with self.assertRaises(ValueError):
            self.workspace.graph("missing")
        with self.assertRaises(ValueError):
            self.workspace.read("missing")
        with self.assertRaises(ValueError):
            self.workspace.search(entity_ids=["missing"])

    def test_entity_scope_does_not_leak_alias_substrings(self):
        self.assertEqual([e["id"] for e in self.workspace.search(entity_ids=["lab"])], ["e-video"])
        self.assertEqual(self.workspace.search("Aster", entity_ids=["lab"]), [])
        self.assertEqual(self.workspace.search(entity_ids=[]), [])
        self.assertNotIn("e-annex", {e["id"] for e in self.workspace.investigate("Aster")["evidence"]})

    def test_search_can_combine_structured_and_document_evidence(self):
        results = self.workspace.search("compute service", entity_ids=["service"])
        self.assertEqual({e["id"] for e in results}, {"e-register", "e-note"})
        self.assertEqual({e["kind"] for e in results}, {"record", "document"})
        self.assertEqual(self.workspace.search("' OR 1=1 --", entity_ids=["service"]), [])

    def test_packet_includes_edge_proof_outside_entity_scope(self):
        packet = self.workspace.investigate("org", 3)
        self.assertNotIn("external", packet["graph"]["node_ids"])
        self.assertEqual({e["id"] for e in packet["evidence"]}, {"e-org", "e-contract", "e-register", "e-note", "e-image", "e-video"})
        self.assertEqual(set(packet["counts_by_kind"]), {"record", "document", "image", "video"})
        self.assertEqual(sum(packet["counts_by_kind"].values()), len(packet["evidence"]))

    def test_conflicts_preserve_both_dated_claims_without_choosing_winner(self):
        packet = self.workspace.investigate("org")
        self.assertEqual(len(packet["conflicts"]), 1)
        conflict = packet["conflicts"][0]
        self.assertEqual((conflict["subject"], conflict["predicate"]), ("service", "operational_status"))
        self.assertEqual(conflict["status"], "unresolved")
        alternatives = {a["value"]: set(a["evidence_ids"]) for a in conflict["alternatives"]}
        self.assertEqual(alternatives, {"operational": {"e-register"}, "unavailable": {"e-note"}})
        dates = {self.workspace.read(i)["date"] for ids in alternatives.values() for i in ids}
        self.assertEqual(dates, {"2026-06-01", "2026-06-02"})
        self.assertNotIn("winner", conflict)
        self.assertNotIn("resolved_value", conflict)

    def test_citations_and_content_hashes_resolve_to_source_material(self):
        packet = self.workspace.investigate("org")
        evidence = {e["id"]: e for e in packet["evidence"]}
        citations = {i for edge in packet["graph"]["edges"] for i in edge["evidence_ids"]}
        citations.update(i for conflict in packet["conflicts"] for alternative in conflict["alternatives"] for i in alternative["evidence_ids"])
        self.assertTrue(citations <= evidence.keys())
        for item in evidence.values():
            self.assertEqual(item["sha256"], hashlib.sha256(item["text"].encode("utf-8")).hexdigest())
            source_path, _, locator = item["source"].partition("#")
            self.assertTrue((self.data / source_path).is_file())
            if item["kind"] == "record":
                self.assertEqual(locator, "row=2")
            else:
                self.assertEqual((self.data / source_path).read_text(encoding="utf-8"), item["text"])

    def test_packet_does_not_inherit_service_status_to_organization(self):
        packet = self.workspace.investigate("org")
        self.assertEqual(packet["mode"], "deterministic_evidence_packet")
        subjects = {a["subject"] for e in packet["evidence"] for a in e.get("assertions", [])}
        self.assertEqual(subjects, {"service"})
        self.assertIn("not proof", packet["graph"]["scope_note"])
        self.assertNotIn("confidence", packet)
        self.assertNotIn("accuracy", packet)
        self.assertNotIn("conclusions", packet)

    def test_graph_edge_must_cite_real_evidence(self):
        self.graph["edges"][0]["evidence_ids"] = ["missing"]
        (self.data / "graph.json").write_text(json.dumps(self.graph), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "existing evidence"):
            Workspace(self.data)

    def test_manifest_cannot_escape_data_directory(self):
        manifest = json.loads((self.data / "manifest.json").read_text(encoding="utf-8"))
        manifest[0]["path"] = "../outside.txt"
        (self.data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "within data directory"):
            Workspace(self.data)


class ShowcaseFixtureTests(unittest.TestCase):
    def test_authored_cases_have_exact_expected_evidence_and_conflicts(self):
        workspace = Workspace(PROJECT / "data")
        self.addCleanup(workspace.close)
        result = evaluate(workspace)
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["passed"], result["total"], result["cases"])
        self.assertIn("not generalization", result["limitations"])


if __name__ == "__main__":
    unittest.main()
