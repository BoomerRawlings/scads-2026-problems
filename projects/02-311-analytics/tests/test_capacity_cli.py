import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CapacityCliTests(unittest.TestCase):
    def invoke(self, *args, expected=0):
        process = subprocess.run([sys.executable, "-m", "analytics311", *args], cwd=ROOT,
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(expected, process.returncode, process.stderr)
        return json.loads(process.stdout if expected == 0 else process.stderr)

    def test_explicit_simulation_does_not_require_dataset_or_create_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "host.json"
            path.write_text(json.dumps({"cpu": {"logical_count": 2, "effective_count": 2},
                "memory": {"total_bytes": 4 * 2**30, "available_bytes": 2**30,
                           "effective_total_bytes": 4 * 2**30, "effective_available_bytes": 2**30},
                "disk": {"total_bytes": 100 * 2**30, "free_bytes": 10 * 2**30}, "warnings": []}), encoding="utf-8")
            result = self.invoke("--config", str(Path(directory) / "missing.json"), "plan-capacity",
                                 "--profile", "scale-lab", "--target-rows", "1000000000", "--inventory", str(path))
            self.assertEqual(1_000_000_000, result["target_rows"])
            self.assertEqual("scale-lab", result["profile"])
            self.assertEqual("insufficient", result["status"])
            self.assertFalse(result["ready_for_production"])
            self.assertEqual([path], list(Path(directory).iterdir()))

    def test_invalid_target_returns_structured_error(self):
        result = self.invoke("plan-capacity", "--target-rows", "0", expected=2)
        self.assertIn("code", result["error"])

    def test_doctor_probes_current_host_without_claiming_capacity(self):
        result = self.invoke("doctor")
        self.assertIn("free_disk_bytes", result)
        self.assertEqual(result["free_disk_bytes"], result["inventory"]["disk"]["free_bytes"])
        self.assertIn("memory", result["inventory"])
        self.assertIn("No services started", result["note"])


if __name__ == "__main__":
    unittest.main()
