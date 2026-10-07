import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from analytics311.errors import AnalyticsError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capacity_scenarios", ROOT / "tools/capacity_scenarios.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class CapacityScenarioTests(unittest.TestCase):
    def setUp(self):
        self.valid = {"schema_version": 1, "evidence_kind": "hypothetical_host_scenarios",
                      "hosts": [{"name": "unknown-host", "inventory": {}}],
                      "row_scenarios": [{"profile": "development", "target_rows": 1000}]}

    def run_input(self, value):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scenarios.json"
            source.write_text(json.dumps(value), encoding="utf-8")
            return runner.run_scenarios(source)

    def test_authored_nine_scenarios_replay_and_bind_exact_source(self):
        source = ROOT / "examples/capacity/scenarios.json"
        report = runner.run_scenarios(source)
        self.assertEqual(report["input_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(report["combination_count"], 9)
        self.assertEqual(report["summary"], {"modeled_fit": 6, "insufficient": 3, "unknown": 0})
        self.assertEqual({row["target_rows"] for row in report["results"]}, {1000, 2000000, 1000000000})
        for row in report["results"]:
            self.assertFalse(row["plan"]["ready_for_production"])
            self.assertEqual(row["plan"]["evidence_kind"], "modeled_capacity")
        self.assertNotIn(str(ROOT), json.dumps(report))

    def test_partial_inventory_reports_unknown_without_probe(self):
        from unittest.mock import patch
        with patch("analytics311.capacity.inventory", side_effect=AssertionError("must not inspect local host")):
            report = self.run_input(self.valid)
        self.assertEqual(report["summary"]["unknown"], 1)
        self.assertFalse(report["ready_for_production"])

    def test_bound_and_bad_types_reject_before_running_plans(self):
        from unittest.mock import patch
        invalid = []
        for key, replacement in (("hosts", []), ("hosts", {}), ("row_scenarios", []), ("schema_version", True)):
            invalid.append({**self.valid, key: replacement})
        repeated = copy.deepcopy(self.valid)
        repeated["hosts"].append(copy.deepcopy(repeated["hosts"][0]))
        invalid.append(repeated)
        invalid.append({**self.valid, "hosts": [{"name": str(i), "inventory": {}} for i in range(101)]})
        invalid.append({**self.valid, "row_scenarios": [{"profile": "development", "target_rows": True}]})
        invalid.append({**self.valid, "hosts": [{"name": "Upper Name", "inventory": {}}]})
        for value in invalid:
            with self.subTest(value=value), patch.object(runner, "plan_capacity", side_effect=AssertionError("must validate first")), self.assertRaises(AnalyticsError):
                self.run_input(value)

    def test_input_byte_cap_and_invalid_json_fail_cleanly(self):
        for content in (b" " * (runner.MAX_INPUT_BYTES + 1), b'{"a":1,"a":2}', b'{"x":NaN}', b"\xff", b"["):
            with self.subTest(length=len(content)), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "input.json"
                source.write_bytes(content)
                with self.assertRaises(AnalyticsError):
                    runner.run_scenarios(source)

    def test_cli_report_is_new_file_and_existing_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.json", Path(directory) / "report.json"
            source.write_text(json.dumps(self.valid), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(["--source", str(source), "--output", str(output)]), 0)
            before = output.read_bytes()
            self.assertEqual(json.loads(before)["combination_count"], 1)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(runner.main(["--source", str(source), "--output", str(output)]), 2)
            self.assertEqual(json.loads(stdout.getvalue())["error"]["code"], "output_exists")
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual({path.name for path in Path(directory).iterdir()}, {"source.json", "report.json"})


if __name__ == "__main__":
    unittest.main()
