"""Small CLI contract checks; no generated workloads or external services."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from analytics311.cli import main


class NormalizeCliTests(unittest.TestCase):
    def test_explicit_limits_reach_normalization_and_its_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            output = Path(directory) / "normalized.jsonl"
            source.write_text('{"unique_key":"one","created_date":"2025-01-01T12:00:00"}\n', encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["normalize", str(source), "--output", str(output),
                               "--max-output-bytes", "4096", "--min-free-bytes", "0"])
            self.assertEqual(status, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["row_count"], 1)
            self.assertEqual(result["bytes"], output.stat().st_size)
            self.assertEqual(result["normalization_limits"], {"max_output_bytes": 4096, "min_free_bytes": 0})

    def test_invalid_limit_is_structured_error_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.jsonl"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["normalize", str(Path(directory) / "missing.jsonl"),
                               "--output", str(output), "--max-output-bytes", "0"])
            self.assertEqual(status, 2)
            self.assertIn("code", json.loads(stderr.getvalue())["error"])
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".jsonl.part").exists())


if __name__ == "__main__":
    unittest.main()
