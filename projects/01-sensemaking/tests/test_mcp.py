"""Protocol smoke test: real SDK client -> stdio process -> workspace tools."""

from __future__ import annotations

import csv
import base64
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
HAS_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the MCP transport")
class MCPTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_workflow_and_errors(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile(mode="w+") as errlog:
            data = Path(directory)
            self._write_fixture(data)
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(PROJECT_DIR / "mcp_server.py"), "--data-dir", str(data)],
            )
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                    initialized = await client.initialize()
                    self.assertEqual(initialized.serverInfo.name, "scads-sensemaking")
                    self.assertIn("untrusted source material", initialized.instructions)

                    catalog = await client.list_tools()
                    self.assertEqual(
                        {tool.name for tool in catalog.tools},
                        {"entity_search", "traverse_relationships", "search_evidence",
                         "read_evidence", "inspect_media", "read_media"},
                    )
                    self.assertTrue(all(tool.annotations.readOnlyHint for tool in catalog.tools))

                    found = await client.call_tool("entity_search", {"query": "shared alias"})
                    self.assertFalse(found.isError)
                    self.assertTrue(found.structuredContent["ambiguous"])
                    self.assertEqual(len(found.structuredContent["matches"]), 2)

                    ambiguous = await client.call_tool("traverse_relationships", {"target": "shared alias"})
                    self.assertTrue(ambiguous.isError)
                    graph = await client.call_tool("traverse_relationships", {"target": "org", "max_hops": 2})
                    self.assertFalse(graph.isError)
                    self.assertEqual(graph.structuredContent["paths"]["supplier"], ["org", "lab", "supplier"])

                    evidence = await client.call_tool(
                        "search_evidence", {"query": "sensor", "entity_ids": graph.structuredContent["node_ids"]}
                    )
                    self.assertFalse(evidence.isError)
                    self.assertEqual({e["id"] for e in evidence.structuredContent["evidence"]}, {"r-sensor", "d-note"})
                    self.assertNotIn("inventory", evidence.structuredContent)
                    inventory = await client.call_tool("search_evidence", {"entity_ids": ["org", "lab", "supplier"]})
                    self.assertEqual(inventory.structuredContent["inventory"],
                                     {"mode": "unpaginated", "complete": True, "entity_ids": ["lab", "org", "supplier"]})

                    record = await client.call_tool("read_evidence", {"evidence_id": "d-note"})
                    self.assertEqual(record.structuredContent["source"], "note.txt")
                    self.assertIn("Sensor", record.structuredContent["text"])
                    metadata = await client.call_tool("inspect_media", {"evidence_id": "d-note"})
                    self.assertFalse(metadata.structuredContent["available"])
                    self.assertEqual(metadata.structuredContent["extraction"], "authored_fixture")

                    pixels = await client.call_tool("read_media", {"evidence_id": "i-probe"})
                    self.assertFalse(pixels.isError)
                    images = [block for block in pixels.content if block.type == "image"]
                    self.assertEqual(len(images), 1)
                    self.assertEqual(images[0].mimeType, "image/png")
                    self.assertTrue(base64.b64decode(images[0].data).startswith(b"\x89PNG\r\n\x1a\n"))

                    empty = await client.call_tool("search_evidence", {"entity_ids": []})
                    self.assertEqual(empty.structuredContent["evidence"], [])
                    self.assertEqual(empty.structuredContent["inventory"]["entity_ids"], [])
                    for tool, arguments in [
                        ("read_evidence", {"evidence_id": "missing"}),
                        ("traverse_relationships", {"target": "org", "max_hops": -1}),
                        ("traverse_relationships", {"target": "org", "max_hops": True}),
                        ("traverse_relationships", {"target": "org", "max_hops": 1.5}),
                        ("search_evidence", {"entity_ids": ["missing"]}),
                        ("read_media", {"evidence_id": "i-probe", "timestamps": [True]}),
                    ]:
                        failure = await client.call_tool(tool, arguments)
                        self.assertTrue(failure.isError, (tool, failure))

    @staticmethod
    def _write_fixture(data: Path) -> None:
        from PIL import Image

        graph = {
            "nodes": [
                {"id": "org", "name": "Research Group", "aliases": []},
                {"id": "lab", "name": "Field Lab", "aliases": ["shared alias"]},
                {"id": "supplier", "name": "Sensor Supplier", "aliases": ["shared alias"]},
            ],
            "edges": [
                {"source": "org", "target": "lab", "relation": "contains", "evidence_ids": ["d-note"]},
                {"source": "lab", "target": "supplier", "relation": "supplied_by", "evidence_ids": ["d-note"]},
            ],
        }
        (data / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
        with (data / "records.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["id", "entity_id", "title", "date", "text", "subject", "predicate", "value"])
            writer.writerow(["r-sensor", "supplier", "Sensor inventory", "2026-01-01", "Sensor shipment ready", "supplier", "status", "ready"])
        (data / "note.txt").write_text("Research Group contains Field Lab. Sensor Supplier supplies Field Lab.", encoding="utf-8")
        Image.new("RGB", (8, 8), color=(10, 20, 30)).save(data / "probe.png")
        (data / "probe.txt").write_text("Authored image metadata.", encoding="utf-8")
        manifest = [{
            "id": "d-note", "entity_ids": ["org", "lab", "supplier"], "kind": "document",
            "title": "Supplier note", "date": "2026-01-02", "path": "note.txt",
            "assertions": [], "extraction": "authored_fixture",
        }, {
            "id": "i-probe", "entity_ids": ["org"], "kind": "image_annotation",
            "title": "Raw media probe", "date": "2026-01-02", "path": "probe.txt",
            "assertions": [], "extraction": "authored_fixture", "media_path": "probe.png",
        }]
        (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
