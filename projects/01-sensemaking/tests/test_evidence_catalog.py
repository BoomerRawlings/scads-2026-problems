import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from evidence_catalog import (CatalogError, EvidenceCatalog, MetadataItemTooLarge,
                              StaleCatalogError, catalog_json_bytes, validate_catalog_chain)
from sensemaking import Workspace


class EvidenceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="evidence-catalog-test-")
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "input"
        self.data.mkdir()
        self.write_json("graph.json", {"nodes": [{"id": value, "name": value, "aliases": []}
                                                for value in ("alpha", "beta", "empty")], "edges": []})
        self.write_json("dataset.json", {"id": "catalog-test", "kind": "synthetic", "version": "1"})
        with (self.data / "records.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("id", "entity_id", "title", "date", "text",
                                                       "subject", "predicate", "value"))
            writer.writeheader()
            for number in range(6):
                writer.writerow({"id": f"record-{number}", "entity_id": "alpha" if number % 2 == 0 else "beta",
                                 "title": f"Record {number} café", "date": "2025-01-02", "text": f"Row {number}",
                                 "subject": "alpha", "predicate": "private_predicate", "value": "PRIVATE_ASSERTION"})
        (self.data / "documents").mkdir()
        self.hidden_text = "HIDDEN_TEXT_CONTENT " + "雪" * 100000
        (self.data / "documents/first.txt").write_text(self.hidden_text, encoding="utf-8")
        (self.data / "documents/second.txt").write_text("Different complete text", encoding="utf-8")
        (self.data / "attachment.bin").write_bytes(b"declared media bytes")
        self.manifest = [
            {"id": "document-1", "entity_ids": ["alpha", "beta"], "title": "Exact title café",
             "kind": "text", "date": "2025-02-03", "path": "documents/first.txt",
             "assertions": [{"subject": "alpha", "predicate": "private_predicate", "value": "PRIVATE_ASSERTION"}],
             "media_path": "attachment.bin", "unlisted_metadata": "DO_NOT_PUBLISH"},
            {"id": "document-2", "entity_ids": ["beta"], "title": "Another source", "kind": "text",
             "date": "2025-02-04", "path": "documents/second.txt", "assertions": []},
        ]
        self.write_json("manifest.json", self.manifest)

    def write_json(self, relative, value):
        (self.data / relative).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def exchanges(self, catalog, **options):
        result, cursor = [], None
        while True:
            response = catalog.page(cursor=cursor, **options)
            result.append({"cursor": cursor, "response": response})
            cursor = response["next_cursor"]
            if cursor is None:
                return result

    def test_complete_chain_exact_metadata_no_evidence_credit(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=2)
            self.assertEqual(len(calls), 4)
            result = validate_catalog_chain(catalog, calls, max_items=2)
            self.assertEqual(result["item_count"], 8)
            self.assertTrue(result["scope_inventory_complete"])
            self.assertTrue(result["metadata_only"])
            self.assertFalse(result["evidence_content_returned"])
            items = [item for call in calls for item in call["response"]["items"]]
            self.assertEqual([item["id"] for item in items], sorted(item["id"] for item in items))
            first = items[0]
            self.assertEqual(set(first), {"id", "title", "kind", "date", "entity_ids", "source",
                                          "text_sha256", "text_bytes"})
            self.assertEqual(first["title"], "Exact title café")
            self.assertEqual(first["source"], "documents/first.txt")
            self.assertEqual(first["entity_ids"], ["alpha", "beta"])
            self.assertEqual(first["text_bytes"], len(self.hidden_text.encode("utf-8")))
            self.assertEqual(first["text_sha256"], hashlib.sha256(self.hidden_text.encode("utf-8")).hexdigest())
            serialized = catalog_json_bytes(calls)
            for private in (b"HIDDEN_TEXT_CONTENT", b"PRIVATE_ASSERTION", b"private_predicate",
                            b"DO_NOT_PUBLISH", b"media_path", b"assertions"):
                self.assertNotIn(private, serialized)

    def test_page_item_and_utf8_byte_bounds(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=8, max_bytes=1100)
            self.assertGreater(len(calls), 1)
            for call in calls:
                page = call["response"]
                self.assertLessEqual(len(page["items"]), 8)
                self.assertLessEqual(len(catalog_json_bytes(page)), 1100)
                self.assertEqual(page["total_items"], 8)
            self.assertEqual(validate_catalog_chain(catalog, calls, max_items=8, max_bytes=1100)["item_count"], 8)

    def test_oversized_single_metadata_item_fails_without_truncation(self):
        self.manifest[0]["title"] = "雪" * 1000
        self.write_json("manifest.json", self.manifest)
        with EvidenceCatalog(self.data) as catalog:
            with self.assertRaisesRegex(MetadataItemTooLarge, "document-1"):
                catalog.page(max_bytes=1100)
            item = catalog.page(max_bytes=8192)["items"][0]
            self.assertEqual(item["title"], self.manifest[0]["title"])

    def test_query_and_scope_are_distinct_from_inventory(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, query="HIDDEN_TEXT_CONTENT", entity_ids=["alpha"])
            self.assertEqual(calls[0]["response"]["total_items"], 1)
            self.assertNotIn(b"HIDDEN_TEXT_CONTENT", catalog_json_bytes(calls))
            result = validate_catalog_chain(catalog, calls, query="HIDDEN_TEXT_CONTENT", entity_ids=["alpha"])
            self.assertTrue(result["result_set_complete"])
            self.assertFalse(result["scope_inventory_complete"])

    def test_zero_hit_and_explicit_empty_scope_have_terminal_response(self):
        with EvidenceCatalog(self.data) as catalog:
            for options, inventory in (({"entity_ids": []}, True), ({"entity_ids": ["empty"]}, True),
                                       ({"query": "NO_MATCH"}, False)):
                with self.subTest(options=options):
                    calls = self.exchanges(catalog, **options)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0]["response"]["items"], [])
                    self.assertIsNone(calls[0]["response"]["next_cursor"])
                    result = validate_catalog_chain(catalog, calls, **options)
                    self.assertEqual(result["item_count"], 0)
                    self.assertEqual(result["scope_inventory_complete"], inventory)
            self.assertEqual(catalog.page(entity_ids=None)["total_items"], 8)

    def test_cursor_bound_to_exact_query_scope_and_options(self):
        with EvidenceCatalog(self.data) as catalog:
            cursor = catalog.page(max_items=1)["next_cursor"]
            variants = ({"query": " "}, {"query": "row"}, {"entity_ids": ["alpha"]},
                        {"entity_ids": []}, {"max_items": 2}, {"max_bytes": 4096})
            for changes in variants:
                with self.subTest(changes=changes), self.assertRaises(CatalogError):
                    catalog.page(cursor=cursor, **{"max_items": 1, **changes})
            # Set-equivalent scopes intentionally share a binding, unlike null/all.
            one = catalog.page(entity_ids=["alpha", "beta", "alpha"], max_items=1)
            two = catalog.page(entity_ids=["beta", "alpha"], max_items=1)
            self.assertEqual(one, two)

    def test_stale_snapshot_detects_all_declared_inputs_and_optional_presence(self):
        mutations = ["records.csv", "graph.json", "manifest.json", "dataset.json",
                     "documents/first.txt", "attachment.bin"]
        for relative in mutations:
            with self.subTest(relative=relative):
                path = self.data / relative
                original = path.read_bytes()
                with EvidenceCatalog(self.data) as catalog:
                    cursor = catalog.page(max_items=1)["next_cursor"]
                    path.write_bytes(original + b" ")
                    with self.assertRaises(StaleCatalogError):
                        catalog.page(max_items=1, cursor=cursor)
                path.write_bytes(original)
        media = self.data / "attachment.bin"
        media.unlink()
        with EvidenceCatalog(self.data) as catalog:
            catalog.page()
            media.write_bytes(b"now present")
            with self.assertRaises(StaleCatalogError):
                catalog.page()

    def test_new_catalog_rejects_old_cursor_after_change(self):
        with EvidenceCatalog(self.data) as old:
            cursor = old.page(max_items=1)["next_cursor"]
        (self.data / "documents/second.txt").write_text("Changed", encoding="utf-8")
        with EvidenceCatalog(self.data) as current, self.assertRaises(CatalogError):
            current.page(max_items=1, cursor=cursor)

    def test_snapshot_is_portable_and_pages_are_deterministic(self):
        copied = Path(self.temporary.name) / "elsewhere"
        shutil.copytree(self.data, copied)
        with EvidenceCatalog(self.data) as first, EvidenceCatalog(copied) as second:
            self.assertEqual(self.exchanges(first, max_items=2), self.exchanges(second, max_items=2))

    def test_chain_refuses_replay_skip_reordering_and_shortening(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=2)
            invalid = [[], calls[:-1], calls[1:], [calls[0], calls[0], *calls[1:]],
                       [calls[0], calls[2], calls[1], calls[3]], [*calls, calls[-1]]]
            for chain in invalid:
                with self.subTest(length=len(chain)), self.assertRaises(CatalogError):
                    validate_catalog_chain(catalog, chain, max_items=2)

    def test_valid_later_cursor_alone_never_completes_inventory(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=2)
            later = catalog.page(max_items=2, cursor=calls[-1]["cursor"])
            self.assertIsNone(later["next_cursor"])
            with self.assertRaises(CatalogError):
                validate_catalog_chain(catalog, [{"cursor": calls[-1]["cursor"], "response": later}], max_items=2)
            with self.assertRaises(CatalogError):
                validate_catalog_chain(catalog, [{"cursor": None, "response": later}], max_items=2)

    def test_actual_response_changes_are_rejected(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=2)
            for field, value in (("items", []), ("next_cursor", None), ("total_items", 1),
                                 ("metadata_only", False), ("page_sha256", "0" * 64)):
                damaged = copy.deepcopy(calls)
                damaged[0]["response"][field] = value
                with self.subTest(field=field), self.assertRaises(CatalogError):
                    validate_catalog_chain(catalog, damaged, max_items=2)

    def test_chain_refuses_changed_scope_query_options_or_stale_dataset(self):
        with EvidenceCatalog(self.data) as catalog:
            calls = self.exchanges(catalog, max_items=2)
            for change in ({"query": "row"}, {"entity_ids": ["alpha"]}, {"max_bytes": 4096}, {"max_items": 3}):
                with self.subTest(change=change), self.assertRaises(CatalogError):
                    validate_catalog_chain(catalog, calls, **{"max_items": 2, **change})
            (self.data / "documents/second.txt").unlink()
            with self.assertRaises(StaleCatalogError):
                validate_catalog_chain(catalog, calls, max_items=2)

    def test_malformed_and_arbitrary_offset_cursors_fail(self):
        with EvidenceCatalog(self.data) as catalog:
            cursor = catalog.page(max_items=2)["next_cursor"]
            parts = cursor.split(".")
            wrong_offset = ".".join([*parts[:3], "1", parts[4]])
            wrong_hash = ".".join([*parts[:4], "0" * 64])
            for bad in ("", "1", 2, "x" * 513, wrong_offset, wrong_hash):
                with self.subTest(cursor=bad), self.assertRaises(CatalogError):
                    catalog.page(max_items=2, cursor=bad)

    def test_source_content_reads_remain_separate(self):
        with patch.object(Workspace, "read", side_effect=AssertionError("Catalog must not call full evidence read")):
            with EvidenceCatalog(self.data) as catalog:
                page = catalog.page(query="HIDDEN_TEXT_CONTENT")
                self.assertEqual(page["items"][0]["id"], "document-1")
                self.assertNotIn("text", page["items"][0])
        workspace = Workspace(self.data)
        self.addCleanup(workspace.close)
        self.assertEqual(workspace.read("document-1")["text"], self.hidden_text)
        self.assertIn("assertions", workspace.read("document-1"))

    def test_request_validation_and_closed_catalog(self):
        with EvidenceCatalog(self.data) as catalog:
            for options in ({"max_items": True}, {"max_items": 0}, {"max_items": 101},
                            {"max_bytes": 1023}, {"max_bytes": 65537}, {"max_bytes": True},
                            {"query": None}, {"entity_ids": "alpha"}, {"entity_ids": [None]},
                            {"entity_ids": ["unknown"]}):
                with self.subTest(options=options), self.assertRaises(CatalogError):
                    catalog.page(**options)
        with self.assertRaises(CatalogError):
            catalog.page()

    def test_constructor_refuses_mutation_during_workspace_load(self):
        original_workspace = Workspace
        def changed_workspace(path):
            workspace = original_workspace(path)
            (self.data / "documents/second.txt").write_text("Changed while loading", encoding="utf-8")
            return workspace
        with patch("evidence_catalog.Workspace", side_effect=changed_workspace):
            with self.assertRaises(StaleCatalogError):
                EvidenceCatalog(self.data)

    def test_constructor_refuses_records_missing_from_workspace_search(self):
        self.manifest[0]["kind"] = "record"
        self.write_json("manifest.json", self.manifest)
        workspace = Workspace(self.data)
        self.addCleanup(workspace.close)
        self.assertEqual(workspace.read("document-1")["id"], "document-1")
        self.assertNotIn("document-1", {record["id"] for record in workspace.search()})
        with self.assertRaisesRegex(CatalogError, "complete declared inventory"):
            EvidenceCatalog(self.data)

    def test_page_refuses_mutation_during_search(self):
        with EvidenceCatalog(self.data) as catalog:
            original_search = Workspace.search
            def changed_search(workspace, *args, **kwargs):
                records = original_search(workspace, *args, **kwargs)
                (self.data / "documents/second.txt").write_text("Changed during page construction", encoding="utf-8")
                return records
            with patch.object(Workspace, "search", changed_search):
                with self.assertRaises(StaleCatalogError):
                    catalog.page()


if __name__ == "__main__":
    unittest.main()
