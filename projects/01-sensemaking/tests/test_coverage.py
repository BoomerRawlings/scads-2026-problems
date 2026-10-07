"""Returned-result coverage checks; no model or inferred workspace replay."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_agent import collect_coverage, validate_coverage


def record(evidence_id, entities=None):
    return {"id": evidence_id, "text": "private-source-text", "source": "documents/private.txt",
            "kind": "text", "entity_ids": entities or ["root"]}


def graph(target="root", nodes=None, edges=None, max_hops=1):
    return {"target": {"id": target}, "node_ids": nodes or [target],
            "edges": edges or [], "max_hops": max_hops}


def edge(source, target, *proofs):
    return {"source": source, "target": target, "relation": "contains", "evidence_ids": list(proofs)}


def inventory(entities, records=None):
    return {"query": "", "evidence": records or [],
            "inventory": {"mode": "unpaginated", "complete": True, "entity_ids": entities}}


def event(tool, args, body, *, status="completed", is_error=False, error=None,
          server="sensemaking", structured=False, extra_content=None):
    result = {"content": [{"type": "text", "text": json.dumps(body)}] + (extra_content or []),
              "isError": is_error}
    if structured:
        result["structuredContent"] = body
    return json.dumps({"type": "item.completed", "item": {
        "type": "mcp_tool_call", "server": server, "tool": tool,
        "arguments": args, "status": status, "error": error, "result": result,
    }})


def collect(*events):
    return collect_coverage("\n".join(events), "root")


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.root_graph = event("traverse_relationships", {"target": "root", "max_hops": 1},
                                graph(nodes=["root", "child"], edges=[edge("root", "child", "proof")]))
        self.root_inventory = event("search_evidence", {"query": "", "entity_ids": ["root", "child"]},
                                    inventory(["root", "child"]))
        self.proof = event("read_evidence", {"evidence_id": "proof"}, record("proof", ["registry"]))

    def test_batched_inventory_and_outside_scope_full_proof_complete_ledger(self):
        ledger = collect(self.root_graph, self.root_inventory, self.proof)
        self.assertEqual(ledger["policy"], "returned-graph-coverage-v1")
        self.assertEqual(ledger["target_id"], "root")
        self.assertTrue(ledger["rooted_traversal"])
        self.assertEqual(ledger["scope_entity_ids"], ["child", "root"])
        self.assertEqual(ledger["inventoried_entity_ids"], ["child", "root"])
        self.assertEqual(ledger["required_proof_ids"], ["proof"])
        self.assertEqual(ledger["retrieved_record_ids"], ["proof"])
        self.assertEqual(ledger["traversals"], [{"target_id": "root", "max_hops": 1, "node_count": 2, "edge_count": 1}])
        self.assertEqual(ledger["missing_inventory_entity_ids"], [])
        self.assertEqual(ledger["missing_proof_ids"], [])
        self.assertTrue(ledger["complete"])
        validate_coverage(ledger, "root")

    def test_empty_search_confirms_zero_hits_without_fabricated_records(self):
        ledger = collect(event("traverse_relationships", {"target": "root"}, graph()),
                         event("search_evidence", {"query": "", "entity_ids": ["root"]}, inventory(["root"])))
        self.assertTrue(ledger["complete"])
        self.assertEqual(ledger["retrieved_record_ids"], [])

    def test_filtered_search_can_retrieve_proof_but_never_inventory(self):
        for args_query, returned_query in (("supply", "supply"), ("supply", ""), ("", "supply")):
            body = inventory(["root", "child"], [record("proof")])
            body["query"] = returned_query
            ledger = collect(self.root_graph, event("search_evidence", {
                "query": args_query, "entity_ids": ["root", "child"]}, body))
            with self.subTest(args_query=args_query, returned_query=returned_query):
                self.assertEqual(ledger["retrieved_record_ids"], ["proof"])
                self.assertEqual(ledger["missing_proof_ids"], [])
                self.assertEqual(ledger["missing_inventory_entity_ids"], ["child", "root"])
                self.assertFalse(ledger["complete"])

    def test_partial_and_paginated_search_never_claim_inventory(self):
        mutations = [
            ("inventory", "complete", False), ("inventory", "complete", "true"),
            ("inventory", "mode", "paginated"), ("inventory", "next_cursor", "next-page"),
            ("body", "next_cursor", "next-page"), ("inventory", "truncated", True),
            ("body", "truncated", True),
        ]
        for location, key, value in mutations:
            body = inventory(["root", "child"], [record("proof")])
            (body if location == "body" else body["inventory"])[key] = value
            ledger = collect(self.root_graph, event("search_evidence", {"query": ""}, body))
            with self.subTest(location=location, key=key, value=value):
                self.assertEqual(ledger["inventoried_entity_ids"], [])
                self.assertEqual(ledger["missing_proof_ids"], ["proof"] if location == "body" and key == "truncated" else [])
                self.assertFalse(ledger["complete"])

    def test_inventory_requires_explicit_actual_metadata(self):
        bodies = [{"query": "", "evidence": []}, {"evidence": [], "inventory": inventory(["root"])["inventory"]},
                  {"query": "", "evidence": {}, "inventory": inventory(["root"])["inventory"]}]
        for body in bodies:
            with self.subTest(body=body):
                ledger = collect(self.root_graph, event("search_evidence", {"entity_ids": ["root", "child"]}, body))
                self.assertEqual(ledger["inventoried_entity_ids"], [])

    def test_actual_inventory_subset_not_requested_entities_is_credited(self):
        ledger = collect(self.root_graph, event("search_evidence", {
            "query": "", "entity_ids": ["root", "child"]}, inventory(["root"])), self.proof)
        self.assertEqual(ledger["inventoried_entity_ids"], ["root"])
        self.assertEqual(ledger["missing_inventory_entity_ids"], ["child"])
        # A returned scope contradicting an explicit narrower request is not trusted.
        contradictory = collect(self.root_graph, event("search_evidence", {
            "query": "", "entity_ids": ["root"]}, inventory(["root", "child"])))
        self.assertEqual(contradictory["inventoried_entity_ids"], [])

    def test_global_inventory_credits_returned_entities_without_expanding_graph_scope(self):
        ledger = collect(self.root_graph, event("search_evidence", {"query": ""},
                         inventory(["root", "child", "unrelated"], [record("proof", ["registry"])])))
        self.assertEqual(ledger["scope_entity_ids"], ["child", "root"])
        self.assertEqual(ledger["inventoried_entity_ids"], ["child", "root", "unrelated"])
        self.assertTrue(ledger["complete"])

    def test_failed_calls_and_other_servers_never_supply_coverage(self):
        failures = [{"status": "failed"}, {"status": "in_progress"}, {"is_error": True},
                    {"error": {"message": "failure"}}, {"server": "other"}]
        for failure in failures:
            failed_graph = event("traverse_relationships", {"target": "root"}, graph(), **failure)
            failed_search = event("search_evidence", {"query": ""}, inventory(["root", "child"]), **failure)
            failed_read = event("read_evidence", {"evidence_id": "proof"}, record("proof"), **failure)
            with self.subTest(failure=failure):
                self.assertFalse(collect(failed_graph)["rooted_traversal"])
                self.assertEqual(collect(self.root_graph, failed_search)["inventoried_entity_ids"], [])
                self.assertEqual(collect(self.root_graph, self.root_inventory, failed_read)["missing_proof_ids"], ["proof"])

    def test_returned_graph_scope_not_requested_depth_or_target_is_used(self):
        ledger = collect(event("traverse_relationships", {"target": "outside", "max_hops": 10}, graph(max_hops=0)))
        self.assertEqual(ledger["scope_entity_ids"], ["root"])
        self.assertEqual(ledger["traversals"][0]["max_hops"], 0)
        self.assertTrue(ledger["rooted_traversal"])
        # Requesting the correct root cannot turn an unrelated returned graph into coverage.
        ledger = collect(event("traverse_relationships", {"target": "root"}, graph("outside")))
        self.assertFalse(ledger["rooted_traversal"])
        self.assertEqual(ledger["traversals"], [])

    def test_later_connected_traversal_adds_inventory_and_every_edge_proof_obligations(self):
        pivot = event("traverse_relationships", {"target": "child", "max_hops": 1},
                      graph("child", ["child", "supplier"], [edge("child", "supplier", "supply-proof", "second-proof")]))
        ledger = collect(self.root_graph, self.root_inventory, self.proof, pivot)
        self.assertEqual(ledger["scope_entity_ids"], ["child", "root", "supplier"])
        self.assertEqual(ledger["missing_inventory_entity_ids"], ["supplier"])
        self.assertEqual(ledger["missing_proof_ids"], ["second-proof", "supply-proof"])
        completed = collect(self.root_graph, self.root_inventory, self.proof, pivot,
                            event("search_evidence", {"query": "", "entity_ids": ["supplier"]},
                                  inventory(["supplier"], [record("supply-proof", ["supplier"])])),
                            event("read_evidence", {"evidence_id": "second-proof"}, record("second-proof", ["registry"])))
        self.assertTrue(completed["complete"])

    def test_unrelated_graph_and_comentions_do_not_expand_scope_or_seed_a_pivot(self):
        unrelated = event("traverse_relationships", {"target": "unrelated"},
                          graph("unrelated", ["unrelated", "other"], [edge("unrelated", "other", "unrelated-proof")]))
        mention = event("search_evidence", {"query": "shared", "entity_ids": ["root"]},
                        {"query": "shared", "evidence": [record("shared", ["root", "unrelated"])]})
        ledger = collect(unrelated, self.root_graph, mention, unrelated, self.root_inventory, self.proof)
        self.assertEqual(ledger["scope_entity_ids"], ["child", "root"])
        self.assertEqual(ledger["required_proof_ids"], ["proof"])
        self.assertEqual(len(ledger["traversals"]), 1)
        self.assertTrue(ledger["complete"])

    def test_pivot_before_root_reach_is_ignored_until_actually_repeated(self):
        pivot = event("traverse_relationships", {"target": "child"}, graph("child", ["child", "supplier"]))
        early = collect(pivot, self.root_graph, self.root_inventory, self.proof)
        self.assertTrue(early["complete"])
        self.assertNotIn("supplier", early["scope_entity_ids"])
        repeated = collect(pivot, self.root_graph, self.root_inventory, self.proof, pivot)
        self.assertEqual(repeated["missing_inventory_entity_ids"], ["supplier"])

    def test_metadata_pixels_snippets_and_nested_source_json_are_not_full_edge_proof(self):
        snippets = [{"id": "proof"}, {"id": "proof", "text": "snippet"}]
        snippets += [{key: value for key, value in record("proof").items() if key != omitted}
                     for omitted in ("text", "source", "kind", "entity_ids")]
        snippets.append({**record("proof"), "truncated": True})
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                ledger = collect(self.root_graph, self.root_inventory,
                                 event("search_evidence", {"query": "proof"}, {"query": "proof", "evidence": [snippet]}),
                                 event("read_evidence", {"evidence_id": "proof"}, snippet))
                self.assertEqual(ledger["missing_proof_ids"], ["proof"])
        for tool in ("inspect_media", "read_media", "entity_search"):
            ledger = collect(self.root_graph, self.root_inventory, event(tool, {"evidence_id": "proof"}, record("proof"),
                             extra_content=[{"type": "image", "data": "private-pixels", "mimeType": "image/png"}]))
            with self.subTest(tool=tool):
                self.assertEqual(ledger["missing_proof_ids"], ["proof"])
        nested = record("other")
        nested["nested"] = {"evidence": [record("proof")], "inventory": inventory(["root", "child"])["inventory"]}
        ledger = collect(self.root_graph, event("read_evidence", {"evidence_id": "other"}, nested))
        self.assertEqual(ledger["retrieved_record_ids"], ["other"])
        self.assertEqual(ledger["inventoried_entity_ids"], [])

    def test_structured_envelope_and_json_arguments_supported_without_duplicate_traversal(self):
        ledger = collect(event("traverse_relationships", json.dumps({"target": "root"}), graph(), structured=True),
                         event("search_evidence", json.dumps({"query": "", "entity_ids": ["root"]}),
                               inventory(["root"]), structured=True))
        self.assertTrue(ledger["complete"])
        self.assertEqual(len(ledger["traversals"]), 1)

    def test_ledger_retains_ids_and_counts_never_source_payload_or_pixels(self):
        graph_body = graph(nodes=["root", "child"], edges=[edge("root", "child", "proof")])
        graph_body["target"]["description"] = "private-node-description"
        ledger = collect(event("traverse_relationships", {"target": "root"}, graph_body), self.root_inventory,
                         self.proof, event("read_media", {"evidence_id": "proof"}, record("proof"),
                         extra_content=[{"type": "image", "data": "private-pixels", "mimeType": "image/png"}]))
        saved = json.dumps(ledger)
        for secret in ("private-source-text", "private.txt", "private-node-description", "private-pixels", "mimeType"):
            self.assertNotIn(secret, saved)

    def test_missing_root_cannot_complete_despite_global_inventory(self):
        ledger = collect(event("search_evidence", {"query": ""}, inventory(["root"])))
        self.assertFalse(ledger["complete"])
        with self.assertRaisesRegex(ValueError, "target-rooted"):
            validate_coverage(ledger, "root")

    def test_preflight_reports_first_eight_missing_ids_and_remaining_counts(self):
        nodes = ["root"] + [f"entity-{i:02d}" for i in range(10)]
        edges = [edge("root", nodes[i + 1], f"proof-{i:02d}") for i in range(10)]
        ledger = collect(event("traverse_relationships", {"target": "root"}, graph(nodes=nodes, edges=edges)))
        with self.assertRaises(ValueError) as caught:
            validate_coverage(ledger, "root")
        message = str(caught.exception)
        self.assertIn("inventory entity IDs", message)
        self.assertIn("retrieve full edge proof IDs", message)
        self.assertIn('"entity-07"', message)
        self.assertNotIn('"entity-08"', message)
        self.assertIn('"proof-07"', message)
        self.assertNotIn('"proof-08"', message)
        self.assertIn("(+3 more)", message)
        self.assertIn("(+2 more)", message)

    def test_invalid_or_mismatched_ledger_fails_closed(self):
        complete = collect(self.root_graph, self.root_inventory, self.proof)
        variants = [None, {}, {**complete, "target_id": "other"}, {**complete, "rooted_traversal": False},
                    {**complete, "policy": "unsupported"}, {**complete, "complete": False}]
        for key in ("scope_entity_ids", "inventoried_entity_ids", "required_proof_ids", "retrieved_record_ids"):
            incomplete_shape = copy.deepcopy(complete)
            del incomplete_shape[key]
            variants.extend([incomplete_shape, {**complete, key: "wrong shape"}, {**complete, key: [None]}])
        for ledger in variants:
            with self.subTest(ledger=ledger), self.assertRaises(ValueError):
                validate_coverage(ledger, "root")

    def test_forged_complete_flag_and_empty_missing_lists_cannot_bypass_obligations(self):
        ledger = collect(self.root_graph)
        ledger.update(complete=True, missing_inventory_entity_ids=[], missing_proof_ids=[])
        with self.assertRaisesRegex(ValueError, "Coverage incomplete"):
            validate_coverage(ledger, "root")


if __name__ == "__main__":
    unittest.main()
