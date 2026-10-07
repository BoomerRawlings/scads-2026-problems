"""Actual MCP deficits drive recovery guidance; scripted HTTP is not model accuracy."""
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_local_agent import HAS_MCP, abstention, finish, tool
from tests.test_local_catalog import counted_server, report_with_fixed, write_dataset

if HAS_MCP:
    import local_agent as local


def two_proof_dataset(path):
    write_dataset(path)
    graph = json.loads((path / "graph.json").read_text(encoding="utf-8"))
    graph["edges"][0]["evidence_ids"].append("second-proof")
    (path / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    with (path / "records.csv").open("a", encoding="utf-8") as stream:
        stream.write("second-proof,part,Reciprocal dependency source,2034-01-05,Component records the same dependency,part,dependency,org\n")
    return path


def supported_report():
    report = abstention("org")
    report.update(status="complete", title="Supplied dependency claims", summary="Sources record a dependency.",
                  findings=[{"claim": "The supplied records describe the dependency between the organization and component.",
                             "evidence_ids": ["proof", "second-proof"],
                             "qualification": "Source claims only; independent corroboration is unestablished."}])
    return report


@unittest.skipUnless(HAS_MCP, "Install requirements.txt for actual local HTTP/MCP checks")
class CatalogPlanningGuidanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_proof_only_deficit_recovers_without_repeating_completed_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = two_proof_dataset(base / "data")
            report = supported_report()
            observed_feedback = []

            def read_missing_proof(body):
                observed_feedback.append(body["messages"][-1]["content"])
                return tool("read_evidence", evidence_id="second-proof")

            actions = [tool("entity_search", query="org"),
                       tool("traverse_relationships", target="org", max_hops=1),
                       tool("catalog_evidence", query="", entity_ids=["org", "part"]),
                       tool("read_evidence", evidence_id="proof"), finish(report), read_missing_proof,
                       finish(report), lambda body: report_with_fixed(body, report)]
            with counted_server(actions) as (url, calls):
                output = await local.run("org", base / "run", data_dir=data, base_url=url, max_steps=8,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True)
            feedback, = observed_feedback
            self.assertIn('retrieve full edge proof IDs ["second-proof"]', feedback)
            self.assertIn("through read_evidence", feedback)
            self.assertIn("Reuse completed catalog inventories", feedback)
            self.assertNotIn("Complete an empty-query catalog cursor chain", feedback)
            self.assertNotIn("inventory entity IDs", feedback)
            metadata = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
            trace = json.loads((output / "tool-trace.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["intent_rejections"], 1)
            self.assertEqual(metadata["catalog_planning_guidance_policy"], "question-parts-and-actual-deficits-v1")
            self.assertEqual([entry["name"] for entry in trace].count("catalog_evidence"), 1)
            self.assertEqual(metadata["retrieved_evidence_ids"], ["proof", "second-proof"])
            self.assertTrue(metadata["workflow_coverage"]["complete"])
            self.assertEqual(len(metadata["workflow_coverage"]["catalog_receipts"]), 1)
            self.assertNotIn("UNREAD_BODY_SENTINEL", json.dumps(calls))

    async def test_mixed_deficits_separate_inventory_from_proofs_until_both_satisfied(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = two_proof_dataset(base / "data")
            report = supported_report()
            observed_feedback = []

            def inventory_missing_entity(body):
                observed_feedback.append(body["messages"][-1]["content"])
                return tool("catalog_evidence", query="", entity_ids=["part"])

            def read_missing_proof(body):
                observed_feedback.append(body["messages"][-1]["content"])
                return tool("read_evidence", evidence_id="second-proof")

            actions = [tool("entity_search", query="org"),
                       tool("traverse_relationships", target="org", max_hops=1),
                       tool("catalog_evidence", query="", entity_ids=["org"]),
                       tool("read_evidence", evidence_id="proof"), finish(report), inventory_missing_entity,
                       finish(report), read_missing_proof, finish(report), lambda body: report_with_fixed(body, report)]
            with counted_server(actions) as (url, calls):
                output = await local.run("org", base / "run", data_dir=data, base_url=url, max_steps=10,
                    retrieval_profile="catalog", grounded_media=True, compact_synthesis=True)
            mixed, proof_only = observed_feedback
            self.assertIn('inventory entity IDs ["part"]', mixed)
            self.assertIn('retrieve full edge proof IDs ["second-proof"]', mixed)
            self.assertIn("Complete an empty-query catalog cursor chain", mixed)
            self.assertIn("retain identical query, scope and page options", mixed)
            self.assertIn("through read_evidence", mixed)
            self.assertNotIn("Complete an empty-query catalog cursor chain", proof_only)
            self.assertNotIn("inventory entity IDs", proof_only)
            self.assertIn("through read_evidence", proof_only)
            metadata = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
            trace = json.loads((output / "tool-trace.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["intent_rejections"], 2)
            scopes = [entry["args"]["entity_ids"] for entry in trace if entry["name"] == "catalog_evidence"]
            self.assertEqual(scopes, [["org"], ["part"]])
            self.assertEqual(metadata["workflow_coverage"]["missing_inventory_entity_ids"], [])
            self.assertEqual(metadata["workflow_coverage"]["missing_proof_ids"], [])
            self.assertEqual(metadata["retrieved_evidence_ids"], ["proof", "second-proof"])
            self.assertEqual(len(metadata["workflow_coverage"]["catalog_receipts"]), 2)
            self.assertTrue(metadata["workflow_coverage"]["complete"])
            self.assertNotIn("UNREAD_BODY_SENTINEL", json.dumps(calls))


if __name__ == "__main__":
    unittest.main()
