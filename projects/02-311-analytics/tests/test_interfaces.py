import asyncio
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from analytics311.service import AnalyticsService


ROOT = Path(__file__).resolve().parents[1]


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = Path(self.temporary.name) / "config.json"
        self.config.write_text(json.dumps({"backend": "fixture", "fixture_path": str(ROOT / "fixtures/requests.jsonl"),
                                          "manifest_path": str(ROOT / "fixtures/manifest.json"), "catalog_path": str(ROOT / "config/catalog.json"),
                                          "runs_dir": str(Path(self.temporary.name) / "runs")}), encoding="utf-8")

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, "-m", "analytics311", "--config", str(self.config), *args],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if success else 2, result.stderr)
        return json.loads(result.stdout if success else result.stderr)

    def test_cli_real_process_and_background_export(self):
        result = self.cli("run", "examples/brooklyn-noise.json")
        self.assertEqual(result["total"]["value"], 4)
        self.assertEqual(len(result["rows"]), 2)
        job = self.cli("export", result["result_id"], "--mode", "records", "--cohort", "all_matching")
        stop = time.monotonic() + 20
        while job["status"] in ("queued", "running") and time.monotonic() < stop:
            time.sleep(.1)
            job = self.cli("result", job["job_id"])
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["rows_written"], 4)
        with open(job["file"], encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 4)
        error = self.cli("map", result["result_id"], "--mode", "requests", "--cohort", "all_matching", success=False)
        self.assertEqual(error["error"]["code"], "unsupported_operation")

    def test_default_service_keeps_original_workspace_when_cwd_changes(self):
        original = Path.cwd()
        first = Path(self.temporary.name) / "workspace-a"
        second = Path(self.temporary.name) / "workspace-b"
        first.mkdir()
        second.mkdir()
        processes = []
        launch = subprocess.Popen
        def track_worker(*args, **kwargs):
            process = launch(*args, **kwargs)
            processes.append(process)
            return process
        try:
            with patch.dict(os.environ):
                os.environ.pop("ANALYTICS311_CONFIG", None)
                os.chdir(first)
                service = AnalyticsService()
                self.assertEqual(first / "runs", service.runs)
                spec = json.loads((ROOT / "examples/brooklyn-noise.json").read_text(encoding="utf-8"))
                result = service.run_analysis(spec)
                os.chdir(second)
                with patch("analytics311.service.subprocess.Popen", side_effect=track_worker):
                    job = service.export_csv(result["result_id"], "records", "all_matching")
                stop = time.monotonic() + 60
                while job["status"] in ("queued", "running") and time.monotonic() < stop:
                    time.sleep(.1)
                    job = service.get_result(job["job_id"])
                self.assertEqual("complete", job["status"], job)
                self.assertEqual(4, job["rows_written"])
                self.assertEqual(first / "runs", Path(job["file"]).parent)
                with open(job["file"], encoding="utf-8-sig", newline="") as stream:
                    self.assertEqual(4, len(list(csv.DictReader(stream))))
                self.assertFalse((second / "runs").exists())
                self.assertFalse((first / "runs" / f"{job['job_id']}.export").exists())
                self.assertEqual(1, len(processes))
                self.assertEqual(0, processes[0].wait(timeout=10))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
            os.chdir(original)

    def test_recovery_cli_works_after_dataset_manifest_is_deleted(self):
        manifest = Path(self.temporary.name) / "manifest.json"
        manifest.write_bytes((ROOT / "fixtures/manifest.json").read_bytes())
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["manifest_path"] = str(manifest)
        self.config.write_text(json.dumps(config), encoding="utf-8")
        service = AnalyticsService(self.config)
        spec = json.loads((ROOT / "examples/brooklyn-noise.json").read_text(encoding="utf-8"))
        result = service.run_analysis(spec)
        analysis_path = service.runs / f"{result['result_id']}.json"
        original_analysis = analysis_path.read_bytes()
        # Model a queued worker that died before acquiring its lease.
        with patch("analytics311.service.subprocess.Popen"):
            job = service.export_csv(result["result_id"], "records", "all_matching")
        self.assertEqual("queued", job["status"])
        manifest.unlink()
        recovered = self.cli("recover-exports")
        self.assertEqual([job["job_id"]], [item["job_id"] for item in recovered["recovered"]])
        self.assertEqual(1, recovered["released_reservation_count"])
        final = json.loads((service.runs / f"{job['job_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", final["status"])
        self.assertEqual("worker_interrupted", final["error"]["code"])
        self.assertEqual(original_analysis, analysis_path.read_bytes())

    def test_mcp_stdio_lists_tools_and_matches_direct_service(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest("MCP extra not installed")

        async def exercise():
            parameters = StdioServerParameters(command=sys.executable,
                args=["-m", "analytics311", "--config", str(self.config), "mcp"], cwd=str(ROOT))
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {"describe_dataset", "validate_analysis", "run_analysis", "get_result", "export_csv", "cancel_export", "create_map_link"})
                    described = await session.call_tool("describe_dataset", {})
                    self.assertFalse(described.isError)
                    self.assertEqual(described.structuredContent["dataset"]["dataset_version"], "fixture-v1")
                    spec = json.loads((ROOT / "examples/brooklyn-noise.json").read_text())
                    result = await session.call_tool("run_analysis", {"spec": spec})
                    self.assertFalse(result.isError)
                    direct = AnalyticsService(self.config).run_analysis(spec)
                    self.assertEqual(result.structuredContent["rows"], direct["rows"])
                    self.assertEqual(result.structuredContent["total"], direct["total"])
                    invalid = await session.call_tool("run_analysis", {"spec": {"operation": "delete_index"}})
                    self.assertTrue(invalid.isError)
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
