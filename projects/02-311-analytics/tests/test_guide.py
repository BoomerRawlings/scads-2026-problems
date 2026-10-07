import json
from pathlib import Path
import unittest

from analytics311.contracts import normalize_spec
from analytics311.errors import AnalyticsError
from analytics311.guide import analysis_guide


class AnalysisGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((Path(__file__).resolve().parents[1] / "config" / "catalog.json").read_text(encoding="utf-8"))

    def test_complete_examples_normalize_with_current_catalog_and_caller_version(self):
        guide = analysis_guide("caller-snapshot-v27")
        self.assertEqual(set(guide["examples"]), {"records", "aggregate", "compare_periods"})
        for operation, example in guide["examples"].items():
            with self.subTest(operation=operation):
                normalized = normalize_spec(example, self.catalog)
                self.assertEqual(normalized["operation"], operation)
                self.assertEqual(normalized["dataset_version"], "caller-snapshot-v27")
                self.assertEqual(normalized["as_of"], "2026-01-02T17:00:00+00:00")
        self.assertEqual(normalize_spec(guide["examples"]["records"], self.catalog)["time"],
                         {"field": "created_date", "gte": "2025-12-01T05:00:00+00:00", "lt": "2026-01-01T05:00:00+00:00"})

    def test_documented_geometry_forms_validate(self):
        guide = analysis_guide("some-snapshot-v1")
        for geometry in guide["rules"]["geo"]["forms"]:
            with self.subTest(geometry=geometry["type"]):
                spec = {**guide["examples"]["records"], "geo": geometry}
                self.assertEqual(normalize_spec(spec, self.catalog)["geo"]["type"], geometry["type"])

    def test_guide_contains_no_results_or_fixture_binding_and_is_detached(self):
        guide = analysis_guide("production-v1")
        encoded = json.dumps(guide, allow_nan=False)
        self.assertNotIn("fixture-v1", encoded)
        for example in guide["examples"].values():
            self.assertNotIn("rows", example)
            self.assertNotIn("total", example)
            self.assertNotIn("result_id", example)
        guide["rules"]["fields"]["created_date"] = "broken"
        self.assertEqual(analysis_guide("other-v1")["rules"]["fields"]["created_date"], "date")

    def test_invalid_dataset_versions_are_rejected(self):
        for value in (None, 1, "", "x" * 129):
            with self.subTest(value=value), self.assertRaises(AnalyticsError) as caught:
                analysis_guide(value)
            self.assertEqual(caught.exception.code, "invalid_spec")


if __name__ == "__main__":
    unittest.main()
