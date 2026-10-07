"""Resource/configuration checks; full installed verification is a separate script."""

import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest

from graphrag_discovery import resources


PROJECT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_public_demo_and_schemas_are_available_without_cwd_lookup(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                fixture = json.loads(resources.read_text("fixtures", "pump", "manifest.json"))
                record = json.loads(resources.read_text("schemas", "record.schema.json"))
                assertion = json.loads(resources.read_text("schemas", "assertion.schema.json"))
            finally:
                os.chdir(previous)
        self.assertEqual(fixture["corpus_id"], "pump-fixture")
        self.assertEqual(len(fixture["batches"]), 5)
        self.assertIsInstance(record, dict)
        self.assertIsInstance(assertion, dict)

    def test_resource_directory_context_preserves_fixture_batch_access(self):
        with resources.resource_path("fixtures", "pump") as directory:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            for batch in manifest["batches"]:
                self.assertTrue((directory / batch["records"]).is_file())
                self.assertIsInstance(json.loads((directory / batch["assertions"]).read_text(encoding="utf-8")), list)

    def test_resource_names_cannot_escape_their_declared_directory(self):
        for part in ("..", ".", "../pyproject.toml", "/absolute", "C:\\file", "pump/manifest.json", ""):
            with self.subTest(part=part), self.assertRaises(ValueError):
                resources.read_bytes("fixtures", part)
        with self.assertRaises(ValueError):
            resources.resource_root("runs")

    def test_runtime_metadata_has_no_dependencies_and_declares_assets(self):
        config = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["project"]["dependencies"], [])
        self.assertEqual(config["project"]["version"], "0.3.2")
        self.assertEqual(config["project"]["scripts"]["graphrag-discovery"], "graphrag_discovery.cli:main")
        mappings = config["tool"]["setuptools"]["package-dir"]
        for package, directory in (("graphrag_discovery.fixtures.pump", "fixtures/pump"),
                                   ("graphrag_discovery.schemas", "schemas"),
                                   ("graphrag_discovery.static", "static")):
            self.assertEqual(mappings[package], directory)
            self.assertIn(package, config["tool"]["setuptools"]["packages"])

    def test_bundled_static_entrypoint_exists(self):
        content = resources.read_bytes("static", "index.html")
        self.assertIn(b"<html", content.lower())
        self.assertGreater(len(content), 100)


if __name__ == "__main__":
    unittest.main()
