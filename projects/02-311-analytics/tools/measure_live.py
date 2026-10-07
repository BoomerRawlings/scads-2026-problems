"""Finite real-data measurements and owned export-worker crash/recovery checks."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from analytics311.elastic import ElasticClient, _complete
from analytics311.errors import AnalyticsError
from analytics311.jobs import recover_exports
from analytics311.resources import load_profile
from analytics311.service import AnalyticsService, atomic_json, canonical, read_json


CASES = ("filter", "group", "closure", "geo", "compare")
MAX_CSV_ROWS = 50_000
MAX_CSV_BYTES = 16 * 1024 * 1024
STATS_PATH = ("/_nodes/stats/jvm,process,indices?filter_path=_nodes,nodes.*.jvm.mem,"
              "nodes.*.process.mem,nodes.*.process.cpu,nodes.*.indices.query_cache,"
              "nodes.*.indices.request_cache,nodes.*.indices.search")


def fail(code):
    raise AnalyticsError(code, "Live measurement check failed; inspect the recorded stage.")


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rss_bytes(pid=None):
    """Linux process RSS only; absence is unknown, never zero or virtual memory."""
    try:
        text = Path(f"/proc/{os.getpid() if pid is None else pid}/status").read_text()
        match = re.search(r"^VmRSS:\s+(\d+)\s+kB$", text, re.MULTILINE)
        return int(match[1]) * 1024 if match else None
    except OSError:
        return None


def numeric_tree(value):
    """Keep only bounded numerical measurement fields, excluding node names/hosts."""
    if isinstance(value, dict):
        return {key: numeric_tree(item) for key, item in value.items()
                if isinstance(item, dict) or type(item) in (int, float)}
    return value if type(value) in (int, float) and math.isfinite(value) else None


def node_sample(client, phase):
    raw = client.request("GET", STATS_PATH)
    if (not isinstance(raw.get("_nodes"), dict) or raw["_nodes"].get("failed") != 0
            or not isinstance(raw.get("nodes"), dict) or not 1 <= len(raw["nodes"]) <= 64):
        fail("incomplete_node_measurements")
    nodes = []
    for key, value in sorted(raw["nodes"].items()):
        if not all(isinstance(value.get(metric), dict) for metric in ("jvm", "process", "indices")):
            fail("incomplete_node_measurements")
        for section, field in (("jvm", "heap_used_in_bytes"), ("process", "total_virtual_in_bytes")):
            memory = value[section].get("mem")
            amount = memory.get(field) if isinstance(memory, dict) else None
            if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
                fail("incomplete_node_measurements")
        nodes.append({"node_identity_sha256": digest(key), **numeric_tree(value)})
    return {"phase": phase, "observed_at": datetime.now(timezone.utc).isoformat(),
            "runner_rss_bytes": rss_bytes(), "nodes": nodes}


class Sampler:
    def __init__(self, client, samples):
        self.client, self.samples = client, samples
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.samples.append(node_sample(self.client, "before"))
        def sample():
            while not self.stop.wait(1):
                try:
                    self.samples.append(node_sample(self.client, "during"))
                except AnalyticsError as exc:
                    self.samples.append({"phase": "during", "error_code": exc.code})
                    break
                except Exception as exc:
                    self.samples.append({"phase": "during", "error_code": "sampler_failed", "exception_type": type(exc).__name__})
                    break
        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()

    def finish(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=7)
            if self.thread.is_alive():
                fail("sampler_did_not_stop")
        self.samples.append(node_sample(self.client, "after"))


def inspect_ids(path, *, oracle=False):
    path = Path(path)
    before = path.stat()
    if before.st_size > MAX_CSV_BYTES:
        fail("csv_byte_budget")
    ids = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != ["unique_key"]:
            fail("oracle_schema_mismatch" if oracle else "csv_schema_mismatch")
        for row in reader:
            value = row.get("unique_key")
            if (None in row or not isinstance(value, str) or not value or len(value) > 512
                    or value in ids or len(ids) >= MAX_CSV_ROWS):
                fail("invalid_or_duplicate_csv_membership")
            ids.add(value)
    with path.open("rb") as stream:
        file_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        fail("csv_changed_during_verification")
    return {"rows": len(ids), "bytes": after.st_size, "sha256": file_sha,
            "membership_sha256": digest(sorted(ids))}, ids


def validate_suite(suite):
    if (not isinstance(suite, dict) or set(suite) != {"analyses", "export"}
            or not isinstance(suite["analyses"], dict) or set(suite["analyses"]) != set(CASES)
            or not all(isinstance(value, dict) for value in [*suite["analyses"].values(), suite["export"]])):
        fail("invalid_measurement_suite")
    cases = suite["analyses"]
    closure_metrics = cases["closure"].get("metrics", [])
    if (cases["filter"].get("operation") != "records" or not cases["filter"].get("filters")
            or cases["group"].get("operation") != "aggregate" or not cases["group"].get("group_by")
            or cases["closure"].get("operation") != "aggregate"
            or not isinstance(closure_metrics, list) or not all(isinstance(metric, str) for metric in closure_metrics)
            or not any("closure_hours" in metric for metric in closure_metrics)
            or not cases["geo"].get("geo") or cases["compare"].get("operation") != "compare_periods"
            or suite["export"].get("operation") != "records" or not suite["export"].get("time")):
        fail("measurement_family_missing")
    return suite


def has_real_capture(manifest, depth=0):
    if not isinstance(manifest, dict) or depth > 4:
        return False
    return ((manifest.get("source_kind") == "real_public_records"
             and manifest.get("kind") == "reconciled_public_capture"
             and manifest.get("extraction_complete") is True and manifest.get("observed_complete") is True)
            or has_real_capture(manifest.get("provenance"), depth + 1))


def query_once(config, name, spec):
    started = time.perf_counter()
    service = AnalyticsService(config)
    result = service.run_analysis(spec)
    elapsed = time.perf_counter() - started
    if (result.get("evidence_level") != "elastic_execution" or result.get("execution_complete") is not True
            or result.get("total", {}).get("relation") != "eq"):
        fail("incomplete_query")
    saved = service._load(result["result_id"])
    stable = {key: saved.get(key) for key in ("total", "group_count", "all_rows", "approximate", "comparison_scope")}
    return {"case": name, "seconds": elapsed, "result_sha256": digest(stable), "total": result["total"],
            "group_count": result.get("group_count"), "approximate": result.get("approximate", False),
            "manifest_sha256": digest(service.manifest), "runner_rss_bytes_after": rss_bytes()}


class Workers:
    """Only the Popen handles created by this runner are owned or stopped."""
    def __init__(self, runs):
        self.popen = subprocess.Popen
        self.runs = runs
        self.processes = {}
        self.gate = None
        self.gates = []
        self.peak_rss = None
        self.peak_total_rss = None
        self.peak_owned_handles = 0

    def launch(self, command, **kwargs):
        job_id = command[-1]
        if self.gate is not None:
            command = [sys.executable, str(Path(__file__).resolve()), "_fault-worker",
                       command[command.index("--config") + 1], job_id, str(self.gate)]
            self.gates.append(self.gate)
            self.gate = None
        process = self.popen(command, **kwargs)
        self.processes[job_id] = process
        self.peak_owned_handles = max(self.peak_owned_handles, sum(item.poll() is None for item in self.processes.values()))
        return process

    def sample(self):
        total = []
        for process in self.processes.values():
            if process.poll() is None:
                value = rss_bytes(process.pid)
                if value is not None:
                    self.peak_rss = max(self.peak_rss or 0, value)
                    total.append(value)
        if total:
            self.peak_total_rss = max(self.peak_total_rss or 0, sum(total))

    def cleanup(self):
        errors = []
        for gate in self.gates:
            try:
                gate.with_suffix(".exit").touch()
            except OSError:
                errors.append("fault_exit_signal_failed")
        for job_id, process in self.processes.items():
            try:
                if process.poll() is None:
                    (self.runs / f"{job_id}.cancel").touch()
            except OSError:
                errors.append("worker_cancel_signal_failed")
        for process in self.processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()  # This exact owned handle only; never a metadata PID.
                    errors.append("forced_owned_handle_termination")
                except OSError:
                    errors.append("owned_handle_termination_failed")
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    errors.append("owned_worker_did_not_stop")
                except OSError:
                    errors.append("owned_worker_wait_failed")
            except OSError:
                errors.append("owned_worker_wait_failed")
        return errors


def wait_export(service, job, workers, deadline):
    while job.get("status") in {"queued", "running"}:
        if time.monotonic() >= deadline:
            service.cancel_export(job["job_id"])
            fail("export_measurement_timeout")
        workers.sample()
        process = workers.processes[job["job_id"]]
        if process.poll() is not None and process.returncode != 0:
            fail("export_worker_failed")
        time.sleep(.05)
        job = service.get_result(job["job_id"])
    if job.get("status") != "complete" or job.get("complete") is not True:
        fail("export_incomplete")
    workers.processes[job["job_id"]].wait(timeout=max(.01, min(10, deadline - time.monotonic())))
    if workers.processes[job["job_id"]].returncode != 0:
        fail("export_worker_failed")
    measured, _ = inspect_ids(job["file"])
    if measured["rows"] != job.get("rows_written") or measured["sha256"] != job.get("sha256"):
        fail("csv_integrity_mismatch")
    return measured


def fault_worker(config, job_id, gate):
    """Hold the actual real-index worker after its first row, then abrupt exit86."""
    service = AnalyticsService(config)
    original = service.backend.iter_records
    def gated(*args, **kwargs):
        records = original(*args, **kwargs)
        try:
            yield next(records)
            Path(gate).write_text(json.dumps({"pid": os.getpid(), "rss_bytes": rss_bytes()}), encoding="utf-8")
            until = time.monotonic() + 120
            while time.monotonic() < until:
                if Path(gate).with_suffix(".exit").exists():
                    os._exit(86)
                time.sleep(.05)
            fail("fault_gate_timeout")
        finally:
            records.close()
    service.backend.iter_records = gated
    service.run_export_job(job_id)


def run_measurements(config_path, suite_path, output_path, work_dir, oracle_csv, *, repeats=5, timeout_seconds=900):
    if type(repeats) is not int or not 1 <= repeats <= 10 or type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 1800:
        fail("invalid_measurement_budget")
    output = Path(output_path)
    work = Path(work_dir).resolve()
    if output.exists() or work.exists():
        fail("measurement_output_conflict")
    suite = validate_suite(read_json(suite_path))
    oracle, oracle_ids = inspect_ids(oracle_csv, oracle=True)
    if not oracle_ids:
        fail("empty_recovery_cohort")
    _, config = load_profile(config_path)
    if config.get("backend") != "elastic":
        fail("real_elastic_required")
    work.mkdir(parents=True)
    config.update(runs_dir=str(work / "runs"), export_inline=False)
    budgets = dict(config.get("budgets", {}))
    budgets.update(max_export_rows=min(budgets.get("max_export_rows", MAX_CSV_ROWS), MAX_CSV_ROWS),
                   max_export_bytes=min(budgets.get("max_export_bytes", MAX_CSV_BYTES), MAX_CSV_BYTES),
                   export_deadline_seconds=min(budgets.get("export_deadline_seconds", 180), 180))
    config["budgets"] = budgets
    private_config = work / "profile.json"
    atomic_json(private_config, config)
    started = time.monotonic()
    deadline = started + timeout_seconds
    report = {"schema_version": 1, "evidence_level": "measured_real_elasticsearch_workload", "passed": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "suite_sha256": digest(suite),
              "options": {"repeats": repeats, "query_concurrency": [1, 2], "timeout_seconds": timeout_seconds,
                          "max_export_rows": budgets["max_export_rows"], "max_export_bytes": budgets["max_export_bytes"]},
              "oracle": oracle, "queries": [], "concurrency": [], "memory_samples": [], "checks": {},
              "limitations": ["Finite workload observations; no SLA, tail-latency or maximum-capacity claim.",
                              "Cache state is uncontrolled. Serial repeats precede concurrency1, concurrency2, exports and recovery.",
                              "Fresh service instances share the same Elasticsearch cache/index; no cache-clearing or index restart.",
                              "Query digests test repeatability, not an independent semantic oracle; CSV uses separately supplied membership.",
                              "Node process memory is virtual memory, not RSS. Runner/owned-worker RSS comes from Linux procfs when available.",
                              "Sampling adds overhead and may miss peaks; client timing includes fresh service initialization and result persistence.",
                              "Timeouts are cooperative: already running query I/O may outlast the deadline; queued futures are cancelled on failure.",
                              "Owned launch-handle overlap is process overlap, not proof of simultaneous row serialization or CPU execution.",
                              "Abrupt worker recovery covers local leases/files only; abandoned PIT expires on the server."]}
    sampler = workers = None
    stage = "preflight"
    try:
        service = AnalyticsService(private_config)
        manifest = service.manifest
        if (manifest.get("immutable") is not True or type(manifest.get("row_count")) is not int
                or manifest["row_count"] < 2_000_000 or not has_real_capture(manifest)):
            fail("real_million_snapshot_required")
        actual_count = service.backend.client.request("GET", f"/{config['index']}/_count")
        _complete(actual_count, search=False)
        if actual_count.get("count") != manifest["row_count"]:
            fail("snapshot_count_mismatch")
        report["snapshot"] = {key: manifest.get(key) for key in ("dataset_version", "index_uuid", "row_count", "immutable")}
        report["snapshot"]["manifest_sha256"] = digest(manifest)
        version = service.backend.client.request("GET", "/").get("version", {}).get("number")
        if not isinstance(version, str) or not version:
            fail("server_version_missing")
        report["elasticsearch_version"] = version
        for spec in [*suite["analyses"].values(), suite["export"]]:
            service.validate_analysis(spec)
        samples_client = ElasticClient(config["elastic_url"], allow_insecure_local=config.get("allow_insecure_local", False), timeout=5)
        sampler = Sampler(samples_client, report["memory_samples"])
        sampler.start()
        baseline = {}
        stage = "serial_queries"
        for name in CASES:
            for number in range(repeats):
                if time.monotonic() >= deadline:
                    fail("measurement_timeout")
                trial = query_once(private_config, name, suite["analyses"][name])
                trial["repeat"] = number + 1
                report["queries"].append(trial)
                baseline.setdefault(name, trial["result_sha256"])
                if trial["result_sha256"] != baseline[name] or trial["manifest_sha256"] != digest(manifest):
                    fail("query_result_drift")
        report["latency_summary"] = {name: {"runs": repeats,
            "median_seconds": statistics.median(row["seconds"] for row in report["queries"] if row["case"] == name),
            "maximum_seconds": max(row["seconds"] for row in report["queries"] if row["case"] == name)} for name in CASES}
        stage = "query_concurrency"
        for concurrency in (1, 2):
            if time.monotonic() >= deadline:
                fail("measurement_timeout")
            begin = time.perf_counter()
            batch = {"concurrency": concurrency, "trials": []}
            report["concurrency"].append(batch)
            pool = ThreadPoolExecutor(max_workers=concurrency)
            futures = []
            try:
                futures = [pool.submit(query_once, private_config, name, suite["analyses"][name]) for name in CASES]
                for future in futures:
                    trial = future.result(timeout=max(.01, deadline - time.monotonic()))
                    batch["trials"].append(trial)
                    if trial["result_sha256"] != baseline[trial["case"]] or trial["manifest_sha256"] != digest(manifest):
                        fail("concurrent_result_drift")
            finally:
                for future in futures:
                    future.cancel()
                pool.shutdown(wait=True, cancel_futures=True)
            batch["elapsed_seconds"] = time.perf_counter() - begin
            batch["observed_queries_per_second"] = len(CASES) / batch["elapsed_seconds"]
        report["checks"]["query_results_stable"] = True
        stage = "export"
        result = service.run_analysis(suite["export"])
        if result["total"]["value"] != oracle["rows"]:
            fail("export_oracle_count_mismatch")
        workers = Workers(service.runs)
        with patch("analytics311.service.subprocess.Popen", workers.launch):
            begin = time.perf_counter()
            job = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
            exported = wait_export(service, job, workers, min(deadline, time.monotonic() + 180))
            exported["seconds"] = time.perf_counter() - begin
            exported["independent_membership_equal"] = exported["membership_sha256"] == oracle["membership_sha256"]
            report["export"] = exported
            if not exported["independent_membership_equal"]:
                fail("export_oracle_membership_mismatch")
            stage = "concurrent_exports"
            begin = time.perf_counter()
            jobs, overlap_observations = [], []
            for _ in range(2):
                jobs.append(service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"]))
                overlap_observations.append(sum(workers.processes[item["job_id"]].poll() is None for item in jobs))
            exports = [wait_export(service, item, workers, min(deadline, time.monotonic() + 180)) for item in jobs]
            report["concurrent_exports"] = {"requested_concurrency": 2, "elapsed_seconds": time.perf_counter() - begin,
                                             "peak_observed_live_owned_launch_handles": max(overlap_observations), "exports": exports}
            report["checks"]["concurrent_export_launch_overlap"] = max(overlap_observations) == 2
            if any(item["membership_sha256"] != oracle["membership_sha256"] for item in exports):
                fail("concurrent_export_oracle_membership_mismatch")
            stage = "abrupt_worker_recovery"
            gate = work / "fault.ready"
            workers.gate = gate
            crashed = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
            process = workers.processes[crashed["job_id"]]
            wait_until = min(deadline, time.monotonic() + 90)
            while not gate.exists():
                workers.sample()
                if process.poll() is not None or time.monotonic() >= wait_until:
                    fail("fault_worker_did_not_reach_real_row")
                time.sleep(.05)
            active = recover_exports(service.runs)
            if active.get("active_count") != 1 or active.get("recovered_count") != 0:
                fail("active_worker_not_protected")
            gate.with_suffix(".exit").touch()
            process.wait(timeout=15)
            if process.returncode != 86:
                fail("actual_interpreter_exit_not_verified")
            begin = time.perf_counter()
            recovered = recover_exports(service.runs)
            terminal = service.get_result(crashed["job_id"])
            residue = any((service.runs / f"{crashed['job_id']}{suffix}").exists() for suffix in (".csv.part", ".csv", ".export"))
            recovery = {"actual_interpreter_exit": process.returncode, "active_worker_protected": True,
                        "worker_reported_rss_bytes_at_gate": read_json(gate).get("rss_bytes"),
                        "seconds": time.perf_counter() - begin, "recovered_count": recovered.get("recovered_count"),
                        "terminal_status": terminal.get("status"), "terminal_error_code": terminal.get("error", {}).get("code"),
                        "partial_and_reservation_removed": not residue}
            report["recovery"] = recovery
            if (recovered.get("recovered_count") != 1 or recovered.get("invalid_count") != 0 or residue
                    or [item.get("job_id") for item in recovered.get("recovered", [])] != [crashed["job_id"]]
                    or recovered["recovered"][0].get("removed_partial") is not True
                    or recovered.get("released_reservations") != [crashed["job_id"]]
                    or terminal.get("status") != "failed" or terminal.get("error", {}).get("code") != "worker_interrupted"):
                fail("recovery_failed")
            stage = "reexport"
            begin = time.perf_counter()
            repeat_job = service.export_csv(result["result_id"], "records", "all_matching", columns=["unique_key"])
            reexport = wait_export(service, repeat_job, workers, min(deadline, time.monotonic() + 180))
            reexport["seconds"] = time.perf_counter() - begin
            reexport["independent_membership_equal"] = reexport["membership_sha256"] == oracle["membership_sha256"]
            report["reexport"] = reexport
            if not reexport["independent_membership_equal"]:
                fail("reexport_oracle_membership_mismatch")
        report["checks"].update(independent_csv_membership=True, actual_worker_recovery=True)
        if not report["checks"]["concurrent_export_launch_overlap"]:
            fail("concurrent_export_overlap_not_observed")
        report["passed"] = True
    except Exception as exc:
        report["error"] = {"stage": stage, "code": exc.code if isinstance(exc, AnalyticsError) else "measurement_failed",
                           "exception_type": type(exc).__name__}
    finally:
        if workers:
            try:
                errors = workers.cleanup()
                if errors:
                    report["cleanup_errors"] = errors
                    report["passed"] = False
            except Exception as exc:
                report["cleanup_errors"] = [type(exc).__name__]
                report["passed"] = False
            report["owned_worker_peak_sampled_rss_bytes"] = workers.peak_rss
            report["owned_workers_peak_sampled_total_rss_bytes"] = workers.peak_total_rss
            report["peak_live_owned_launch_handles"] = workers.peak_owned_handles
        if sampler:
            try:
                sampler.finish()
                healthy = all("error_code" not in item for item in report["memory_samples"])
                report["checks"]["node_memory_observations_complete"] = healthy
                if not healthy:
                    report["passed"] = False
            except Exception as exc:
                report["memory_error"] = exc.code if isinstance(exc, AnalyticsError) else type(exc).__name__
                report["passed"] = False
        report["elapsed_seconds"] = time.monotonic() - started
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "suite", "output", "work-dir", "oracle-csv"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_measurements(args.config, args.suite, args.output, args.work_dir, args.oracle_csv,
                                  repeats=args.repeats, timeout_seconds=args.timeout_seconds)
    except AnalyticsError as exc:
        print(json.dumps({"passed": False, "error_code": exc.code}))
        return 2
    print(json.dumps({"passed": result["passed"], "checks": result["checks"], "error": result.get("error")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "_fault-worker":
        fault_worker(*sys.argv[2:])
    else:
        raise SystemExit(main())
