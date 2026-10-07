"""Offline source-unit fidelity and unchanged Workspace boundary checks."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import import_public_data as legacy
from scripts import import_public_statements as units
from sensemaking import Workspace


class PublicStatementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.capture_bytes = legacy.load_sources(legacy.capture.DEFAULT_OUTPUT)
        cls.files, cls.totals = units.build_dataset(cls.sources, cls.capture_bytes)
        cls.manifest = json.loads(cls.files["manifest.json"])
        cls.records = {item["id"]: json.loads(cls.files[item["path"]]) for item in cls.manifest}
        cls.by_entity = {legacy.node_id(source["spec"]["provider"], source["spec"]["entity_id"]): source for source in cls.sources}

    def test_determinism_raw_bytes_and_source_objects_preserved(self):
        originals = copy.deepcopy(self.sources)
        repeated, totals = units.build_dataset(self.sources, self.capture_bytes)
        self.assertEqual(repeated, self.files)
        self.assertEqual(totals, self.totals)
        self.assertEqual(self.sources, originals)
        self.assertEqual(self.files["sources/capture-manifest.json"], self.capture_bytes)
        for source in self.sources:
            self.assertEqual(self.files["sources/" + source["entry"]["path"]], source["raw"])

    def test_every_selected_statement_and_relationship_preserves_exact_json(self):
        actual = set()
        for record in self.records.values():
            if record["record_type"] == "crosswalk":
                continue
            provenance = record["source_provenance"]
            raw = self.files[provenance["path"]]
            self.assertEqual(legacy.capture.digest(raw), provenance["sha256"])
            source = next(source for source in self.sources if source["entry"]["id"] == provenance["id"])
            self.assertEqual(provenance["revision"], source["entry"]["revision"])
            for fragment in record["source_fragments"]:
                self.assertEqual(fragment["value"], units.pointer_value(json.loads(raw), fragment["json_pointer"]))
                if record["record_type"] in {"statement", "relationship", "external-id"}:
                    actual.add((provenance["id"], fragment["json_pointer"]))
        expected = set()
        for source in self.sources:
            spec, entity = source["spec"], source["entity"]
            if spec["provider"] == "ror":
                for field in ("relationships", "external_ids"):
                    expected.update((spec["id"], f"/{field}/{index}") for index in range(len(entity.get(field, []))))
            else:
                for prop, values in entity["claims"].items():
                    if prop in legacy.INDEXED_PROPERTIES:
                        expected.update((spec["id"], f"/entities/{spec['entity_id']}/claims/{prop}/{index}") for index in range(len(values)))
        self.assertEqual(actual, expected)
        self.assertTrue(all(item["assertions"] == [] for item in self.manifest))
        # Exact equality above includes every qualifier, reference, rank, GUID and unknown-value snak.
        qualified = [record for record in self.records.values() if record["record_type"] == "statement"
                     and record["source_fragments"][0]["value"].get("qualifiers")]
        self.assertTrue(qualified)

    def test_identity_fields_retained_with_exact_pointers_without_false_event_dates(self):
        identities = [record for record in self.records.values() if record["record_type"] == "identity"]
        self.assertEqual(len(identities), 12)
        for record in identities:
            origin = record["source_provenance"]
            source = next(source for source in self.sources if source["spec"]["id"] == origin["id"])
            fields = (tuple(sorted(set(source["entity"]) - {"relationships", "external_ids"})) if source["spec"]["provider"] == "ror"
                      else ("id", "type", "lastrevid", "modified", "labels", "aliases", "descriptions"))
            self.assertEqual({fragment["json_pointer"].rsplit("/", 1)[-1] for fragment in record["source_fragments"]},
                             {field for field in fields if field in source["entity"]})
        self.assertTrue(all("not assertion validity" in item["date_meaning"] for item in self.manifest))

    def test_exact_edge_proofs_and_exclusions_match_conservative_projection(self):
        old, _ = legacy.build_dataset(self.sources, self.capture_bytes)
        graph = json.loads(self.files["graph.json"])
        old_graph = json.loads(old["graph.json"])
        self.assertEqual(graph["nodes"], old_graph["nodes"])
        self.assertEqual([{k: v for k, v in edge.items() if k != "evidence_ids"} for edge in graph["edges"]],
                         [{k: v for k, v in edge.items() if k != "evidence_ids"} for edge in old_graph["edges"]])
        for edge in graph["edges"]:
            self.assertEqual(len(edge["evidence_ids"]), 2)
            for eid in edge["evidence_ids"]:
                proof = self.records[eid]
                self.assertEqual(proof["record_type"], "relationship")
                self.assertEqual(proof["projection_decision"]["projected_edge"], [edge["source"], edge["target"]])
                self.assertEqual(proof["projection_decision"]["exclusion_reasons"], [])
        ledger = json.loads(self.files["projection-ledger.json"])
        old_ledger = json.loads(old["projection-ledger.json"])
        self.assertEqual(len(ledger["decisions"]), len(old_ledger["decisions"]))
        for actual, original in zip(ledger["decisions"], old_ledger["decisions"]):
            self.assertEqual({k: v for k, v in actual.items() if k != "evidence_id"},
                             {k: v for k, v in original.items() if k != "evidence_id"})
        self.assertEqual(ledger["frontier_entity_ids"], old_ledger["frontier_entity_ids"])
        self.assertEqual(self.totals["unindexed_wikidata_statements"], 516)

    def test_crosswalk_candidates_preserve_status_full_claims_and_exact_source_lineage(self):
        ledger = json.loads(self.files["projection-ledger.json"])
        self.assertEqual(len(ledger["crosswalks"]), 9)
        negative = next(row for row in ledger["crosswalks"] if row["wikidata"] == "wikidata:q6973636")
        self.assertEqual(negative["status"], "rejected_list_article_type")
        for candidate in ledger["crosswalks"]:
            self.assertIs(candidate["merged"], False)
            self.assertEqual(self.records[candidate["candidate_evidence_id"]]["candidate"], candidate)
            for claim in candidate["claims"]:
                provenance = claim["source_provenance"]
                source_value = units.pointer_value(json.loads(self.files[provenance["path"]]), claim["source_path"])
                self.assertEqual(claim["source_assertion"], source_value)
                record = self.records[claim["evidence_id"]]
                self.assertEqual(record["source_fragments"][0]["value"], source_value)
            captured = {entity for entity in (candidate["ror"], candidate["wikidata"]) if entity in self.by_entity}
            self.assertEqual({item["source_entity"] for item in candidate["decision_inputs"]}, captured)
            for item in candidate["decision_inputs"]:
                record = self.records[item["evidence_id"]]
                self.assertEqual(record["source_provenance"], item["source_provenance"])
                if item["role"] == "wikidata_type_check":
                    value = units.pointer_value(json.loads(self.files[item["source_provenance"]["path"]]), item["source_path"])
                    self.assertEqual(record["source_fragments"][0]["value"], value)
                    self.assertEqual(item["admissibility_reasons"], legacy.statement_reasons(value))
        self.assertEqual(self.totals["crosswalk_candidates"], 9)

    def test_candidate_decision_identity_binds_non_identifier_classification_source(self):
        original = next(row for row in json.loads(self.files["projection-ledger.json"])["crosswalks"]
                        if row["wikidata"] == "wikidata:q6973636")
        self.assertEqual({row["source_entity"] for row in original["claims"]}, {original["ror"]})
        type_inputs = [row for row in original["decision_inputs"] if row["role"] == "wikidata_type_check"]
        self.assertTrue(any(legacy.item_target(self.records[row["evidence_id"]]["source_fragments"][0]["value"]) == "Q13406463"
                            and not row["admissibility_reasons"] for row in type_inputs))
        changed = copy.deepcopy(self.sources)
        source = next(row for row in changed if row["spec"]["entity_id"] == "Q6973636")
        document = json.loads(source["raw"])
        source["entity"] = document["entities"]["Q6973636"]
        for statement in source["entity"]["claims"]["P31"]:
            if legacy.item_target(statement) == "Q13406463":
                statement["mainsnak"]["datavalue"]["value"] = {"entity-type": "item", "numeric-id": 43229, "id": "Q43229"}
        source["raw"] = units.encoded(document)
        source["entry"]["sha256"] = legacy.capture.digest(source["raw"])
        source["entry"]["size_bytes"] = len(source["raw"])
        revised_files, _ = units.build_dataset(changed, self.capture_bytes)
        revised = next(row for row in json.loads(revised_files["projection-ledger.json"])["crosswalks"]
                       if row["wikidata"] == original["wikidata"])
        self.assertNotEqual(revised["status"], original["status"])
        self.assertNotEqual(revised["candidate_evidence_id"], original["candidate_evidence_id"])
        self.assertEqual(revised["claims"], original["claims"])

    def test_actual_workspace_reads_units_and_resolves_only_source_specific_identities(self):
        with tempfile.TemporaryDirectory() as temporary, patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("offline only")):
            destination = Path(temporary) / "statements"
            units.import_dataset(legacy.capture.DEFAULT_OUTPUT, destination)
            workspace = Workspace(destination)
            try:
                with self.assertRaisesRegex(ValueError, "Ambiguous"):
                    workspace.resolve("National Cancer Institute")
                graph = workspace.graph("ror:040gcmg81", 1)
                self.assertEqual(len(graph["edges"]), 4)
                for edge in graph["edges"]:
                    for eid in edge["evidence_ids"]:
                        self.assertEqual(json.loads(workspace.read(eid)["text"])["record_type"], "relationship")
                selected = workspace.search("P749", ["wikidata:q664846"])
                self.assertTrue(selected)
                self.assertTrue(any("qualified_claim_requires_scope_review" in item["text"] for item in selected))
                self.assertEqual(workspace.graph("wikidata:q664846")["edges"], [])
                all_records = workspace.search()
                self.assertEqual(len(all_records), self.totals["indexed_evidence_records"])
                self.assertEqual(len(json.dumps(all_records, ensure_ascii=False).encode()), self.totals["all_records_json_bytes"])
                self.assertEqual(max(len(json.dumps(item, ensure_ascii=False).encode()) for item in all_records), self.totals["largest_returned_record_bytes"])
            finally:
                workspace.close()

    def test_record_and_dataset_bounds_fail_before_any_publication_without_truncation(self):
        for name, limit, reason in (("MAX_RECORD_BYTES", 256, "record_byte_limit"), ("MAX_OUTPUT_BYTES", 128, "output_byte_limit")):
            with self.subTest(bound=name), tempfile.TemporaryDirectory() as temporary, patch.object(units, name, limit):
                destination = Path(temporary) / "not-created"
                with self.assertRaisesRegex(units.ProjectionError, reason):
                    units.import_dataset(legacy.capture.DEFAULT_OUTPUT, destination)
                self.assertFalse(destination.exists())

    def test_existing_outputs_capture_changes_and_verification_errors_never_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "existing"
            existing.mkdir()
            (existing / "foreign.txt").write_text("preserve")
            with self.assertRaisesRegex(units.ProjectionError, "output_exists"):
                units.import_dataset(legacy.capture.DEFAULT_OUTPUT, existing)
            self.assertEqual((existing / "foreign.txt").read_text(), "preserve")
            destination = Path(temporary) / "not-created"
            changed = copy.deepcopy(self.sources)
            changed[0]["raw"] += b" "
            with patch.object(legacy, "load_sources", side_effect=[(self.sources, self.capture_bytes), (changed, self.capture_bytes)]):
                with self.assertRaisesRegex(units.ProjectionError, "capture_changed"):
                    units.import_dataset(legacy.capture.DEFAULT_OUTPUT, destination)
            with patch.object(legacy, "load_sources", side_effect=ValueError("source_hash_mismatch")):
                with self.assertRaisesRegex(ValueError, "source_hash_mismatch"):
                    units.import_dataset(legacy.capture.DEFAULT_OUTPUT, destination)
            self.assertFalse(destination.exists())

    def test_artifact_hashes_and_default_cli_plan(self):
        manifest = json.loads(self.files["import-manifest.json"])
        self.assertEqual(self.totals["output_bytes_excluding_import_manifest"], sum(len(raw) for name, raw in self.files.items() if name != "import-manifest.json"))
        for item in manifest["files"]:
            self.assertEqual(item["sha256"], legacy.capture.digest(self.files[item["path"]]))
            self.assertEqual(item["size_bytes"], len(self.files[item["path"]]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "not-created"
            stdout = io.StringIO()
            with patch("sys.argv", ["import_public_statements.py", "--output-dir", str(destination)]), redirect_stdout(stdout):
                self.assertEqual(units.main(), 0)
            self.assertEqual(json.loads(stdout.getvalue())["action"], "verified_plan_no_writes")
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
